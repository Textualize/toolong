from __future__ import annotations

from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from rich.text import Text
from datetime import datetime
import json
from typing import Dict, Any
from textual.binding import Binding
from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from eliot.parse import Parser, Task, WrittenAction, WrittenMessage
from pathlib import Path

class EliotTree(Tree):
    """A tree widget for displaying Eliot logs with folding support."""

    DEFAULT_CSS = """
    EliotTree {
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("right", "expand", "Expand", show=False),
        Binding("left", "collapse", "Collapse", show=False),
        Binding("space", "select", "Select", show=False),
    ]

    def __init__(self, file_name: str | None = None) -> None:
        super().__init__(file_name or "Eliot Log")
        self._parser = Parser()
        self._task_nodes: Dict[str, TreeNode] = {}
        self.loading = False

    def _format_node_label(self, eliot_node: Task | WrittenAction | WrittenMessage | tuple) -> Text:
        """Format a node's label based on its type."""
        label = Text()
        
        if isinstance(eliot_node, Task):
            return Text(eliot_node.root().task_uuid)
            
        if isinstance(eliot_node, (WrittenAction, WrittenMessage)):
            # Get action/message type and task level
            message = eliot_node.start_message if isinstance(eliot_node, WrittenAction) else eliot_node
            action_type = message.contents.get("action_type") or message.contents.get("message_type")
            task_level = "/".join(str(n) for n in message.task_level.level)
            
            # Format the label with single slash
            label.append(f"{action_type}/{task_level}", style="cyan")
            
            # Add status and timestamps for actions
            if isinstance(eliot_node, WrittenAction):
                # Add status
                status = "started"
                if eliot_node.end_message:
                    status = eliot_node.end_message.contents.get("action_status", "started")
                status_style = {
                    "succeeded": "green",
                    "failed": "red",
                    "started": "yellow",
                }.get(status, "white")
                label.append(" ⇒ ", style="bright_black")
                label.append(status, style=status_style)
                
                # Add timestamp
                start_time = datetime.fromtimestamp(eliot_node.start_message.timestamp)
                label.append(f" {start_time:%Y-%m-%d %H:%M:%S}Z", style="blue")
                
                # Add duration if action is completed
                if eliot_node.end_message:
                    duration = eliot_node.end_message.timestamp - eliot_node.start_message.timestamp
                    label.append(f" ⧖ {duration:.3f}s", style="blue")
            else:
                # For regular messages, just add timestamp
                msg_time = datetime.fromtimestamp(message.timestamp)
                label.append(f" {msg_time:%Y-%m-%d %H:%M:%S}Z", style="blue")
            
            return label
            
        if isinstance(eliot_node, tuple):
            # Field nodes
            key, value = eliot_node
            if key not in ("task_uuid", "task_level", "action_type", "action_status", "message_type", "timestamp"):
                label.append(f"{key}: ", style="bright_black")
                if key in ("exception", "reason", "error", "failure"):
                    label.append(str(value), style="bright_red")
                else:
                    label.append(str(value), style="white")
                return label
                
        return Text(str(eliot_node))

    def _get_children(self, eliot_node: Task | WrittenAction | WrittenMessage | tuple) -> list:
        """Get children for a node based on its type."""
        if isinstance(eliot_node, Task):
            return [eliot_node.root()]
            
        if isinstance(eliot_node, WrittenAction):
            children = []
            # Add fields from start message
            for key, value in eliot_node.start_message.contents.items():
                if key not in ("task_uuid", "task_level", "action_type", "action_status", "timestamp"):
                    children.append((key, value))
            # Add child actions/messages
            children.extend(eliot_node.children)
            # Add end message fields if present
            if eliot_node.end_message:
                for key, value in eliot_node.end_message.contents.items():
                    if key not in ("task_uuid", "task_level", "action_type", "action_status", "timestamp"):
                        children.append((key, value))
            return children
            
        if isinstance(eliot_node, WrittenMessage):
            # For message nodes, include all fields except the standard ones
            return [(key, value) for key, value in eliot_node.contents.items() 
                   if key not in ("task_uuid", "task_level", "message_type", "timestamp")]

        if isinstance(eliot_node, tuple):
            key, value = eliot_node
            if isinstance(value, dict):
                return list(value.items())
            if isinstance(value, list):
                return list(enumerate(value))
            # For message nodes in the tree, treat them as having their own fields
            if isinstance(key, str) and key.endswith("_details") and isinstance(value, str):
                try:
                    data = json.loads(value)
                    if isinstance(data, dict):
                        return list(data.items())
                except (json.JSONDecodeError, AttributeError):
                    pass
                
        return []

    def _add_node_to_tree(self, eliot_node: Task | WrittenAction | WrittenMessage | tuple, parent: TreeNode | None = None) -> TreeNode:
        """Add an Eliot node to the tree with proper structure."""
        label = self._format_node_label(eliot_node)
        node = (parent or self.root).add(label)
        
        # Get children first to check if node should be expandable
        children = self._get_children(eliot_node)
        
        # Set expansion properties
        node.allow_expand = (
            isinstance(eliot_node, (Task, WrittenAction)) or
            isinstance(eliot_node, WrittenMessage) or
            (isinstance(eliot_node, tuple) and (
                isinstance(eliot_node[1], (dict, list)) or
                (isinstance(eliot_node[1], str) and isinstance(eliot_node[0], str) and eliot_node[0].endswith("_details"))
            ))
        ) and bool(children)  # Only allow expand if there are children
        
        # Auto-expand failed actions
        if isinstance(eliot_node, WrittenAction) and eliot_node.end_message:
            if eliot_node.end_message.contents.get("action_status") == "failed":
                node.expand()
                self._expand_failure_path(node)
        
        # Add children
        for child in children:
            self._add_node_to_tree(child, node)
            
        return node

    def add_log_entry(self, line: str) -> None:
        """Add a log entry to the tree using Eliot's parser."""
        try:
            data = json.loads(line)
            completed_tasks, self._parser = self._parser.add(data)
            
            # Add completed tasks to the tree
            for task in completed_tasks:
                if task.root().task_uuid not in self._task_nodes:
                    node = self._add_node_to_tree(task)
                    self._task_nodes[task.root().task_uuid] = node
                    
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error processing log entry: {e}")

    def _expand_failure_path(self, node: TreeNode) -> None:
        """Expand all nodes in the path to a failure."""
        current = node
        while current and current != self.root:
            current.expand()
            current = current.parent
        self.root.expand()

    def render_node(self, node: TreeNode) -> Text:
        """Render a node with proper formatting."""
        return node.label if isinstance(node.label, Text) else Text(str(node.label))

    def action_expand(self) -> None:
        """Expand the current node."""
        if self.cursor_node and self.cursor_node.allow_expand:
            self.cursor_node.expand()
            
    def action_collapse(self) -> None:
        """Collapse the current node."""
        if self.cursor_node and self.cursor_node.allow_expand:
            self.cursor_node.collapse()
            
    def action_select(self) -> None:
        """Override default select action."""
        pass

class EliotView(Container):
    """Container for EliotTree with basic viewing functionality."""

    DEFAULT_CSS = """
    EliotView {
        width: 1fr;
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.file_paths: list[str] = []
        self._tree = None

    @property
    def tree(self) -> EliotTree:
        """Get the EliotTree instance."""
        return self._tree

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        # Create tree with file name if we have exactly one file
        file_name = Path(self.file_paths[0]).name if len(self.file_paths) == 1 else None
        self._tree = EliotTree(file_name=file_name)
        yield self._tree

    async def on_mount(self) -> None:
        """Handle widget mount."""
        # Process existing log entries
        for path in self.file_paths:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    self._tree.add_log_entry(line)
        
        # Focus the tree
        self._tree.focus() 