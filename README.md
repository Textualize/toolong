

<p align="center">
    <img src="https://github.com/Textualize/toolong/assets/554369/07f286c9-ac8d-44cd-905a-062a26060821" alt="A Kookaburra sitting on a scroll" width="300" >
</p>


[![Discord](https://img.shields.io/discord/1026214085173461072)](https://discord.gg/Enf6Z3qhVr)

# Toolong

A terminal application to view, tail, merge, and search log files (plus JSONL).

<details>  
  <summary> 🎬 Viewing a single file </summary>
    
&nbsp;

<div align="center">
  <video src="https://github.com/Textualize/tailless/assets/554369/a434d427-fa9a-44bf-bafb-1cfef32d65b9" width="400" />
</div>

</details>


## Features

<img width="40%" align="right" alt="Screenshot 2024-02-08 at 13 47 28" src="https://github.com/Textualize/tailless/assets/554369/e4b9e41b-2a42-4cef-b47c-e58a9e4db44a">


- Live tailing of log files.
- Syntax highlights common web server log formats.
- Files don't need to be loaded in to memory, which means it is as fast to open a multiple-gigabyte files as it is to open tiny text file.
- Support for JSONL files: lines are pretty printed.
- Opens .bz and .bz2 files automatically.
- Merges log files by auto detecting timestamps.
  

## Why?

I spent a lot of time in my past life as a web developer working with logs, typically on web servers via ssh.
I would use a variety of tools, but my goto method of analyzing logs was directly on the server with *nix tools like as `tail`, `less`, and `grep` etc.
As useful as these tools are, they are not without friction.

I built `toolong` to be the tool I would have wanted back then.
It is snappy, straightforward to use, and does a lot of the *grunt work* for you.


## Who?

This [guy](https://github.com/willmcgugan). An ex web developer who somehow makes a living writing terminal apps.



## Screenshots

<table>
    <tr>
        <td>
            <img width="100%" alt="Screenshot 2024-02-08 at 13 47 28" src="https://github.com/Textualize/tailless/assets/554369/e4b9e41b-2a42-4cef-b47c-e58a9e4db44a">
        </td>
        <td>
            <img width="100%" alt="Screenshot 2024-02-08 at 13 48 04" src="https://github.com/Textualize/tailless/assets/554369/1a5c3dff-e93c-4746-99d4-2e58f6b44b19">
        </td>
    </tr>
    <tr>
        <td>
            <img width="100%" alt="Screenshot 2024-02-08 at 13 49 22" src="https://github.com/Textualize/tailless/assets/554369/e130a550-579a-4bd1-9281-1cef520634f8">
        </td>
        <td>
            <img width="100%" alt="Screenshot 2024-02-08 at 13 50 04" src="https://github.com/Textualize/tailless/assets/554369/5e620070-4eb8-49e0-9dfa-7ac335b18a62">
        </td>
    </tr>
</table>


## Installing

Toolong is currently best installed with [pipx](https://github.com/pypa/pipx).

```bash
pipx install toolong
```

You could also install Toolong with Pip:

```bash
pip install toolong
```

> [!NOTE] 
> If you use pip, you should ideally create a virtual environment to avoid potential dependancy conflicts.

However you install Toolong, the `tl` command will be added to your path.
Run it to test instalation:

```bash
tl
```

In the near future there will be more installation methods, and hopefully your favorite package manager.

## How to use Toolong

To open a file with Toolong, add the file name(s) as arguments to the command:

```bash
tl mylogfile.log
```

If you add multiple filenames, they will open in tabs.

Added the `--merge` switch to open multiple files and combine them in to a single view:

```bash
tl web.log*
```

In the app, press ++f1++ for additional help.


## Videos

<details>  
  <summary> 🎬 Merging multiple (compressed) files </summary>
&nbsp;

<div align="center">
  <video src="https://github.com/Textualize/tailless/assets/554369/efbbde11-bebf-44ff-8d2b-72a84b542b75" />
</div>
    

</details>

<details>  
  <summary> 🎬 Viewing JSONL files </summary>
&nbsp;

<div align="center">
  <video src="https://github.com/Textualize/tailless/assets/554369/38936600-34ee-4fe1-9fd3-b1581fc3fa37"  />
</div>
    
    

</details>

<details>  
  <summary> 🎬 Live Tailing a file </summary>
&nbsp;

<div align="center">
  <video src="https://github.com/Textualize/tailless/assets/554369/7eea6a0e-b30d-4a94-bb45-c5bff0e329ca" />
</div>


## Installing

Toolong is a Python application, but you don't neccesarily need to be a Python developer to use it.

Toolong is currently best installed with [pipx](https://github.com/pypa/pipx).

```bash
pipx install toolong
```

You could also install Toolong with Pip:

```bash
pip install toolong
```

> [!NOTE] 
> If you use pip, you should ideally create a virtual environment to avoid potential dependancy conflicts.

However you install Toolong, the `tl` command will be added to your path.
Run it to test instalation:

```bash
tl
```

In the near future there will be more installation methods, and hopefully your favorite package manager.

## How to use Toolong

To open a file with Toolong, add the file name(s) as arguments to the command:

```bash
tl mylogfile.log
```

If you add multiple filenames, they will open in tabs.

Added the `--merge` switch to open multiple files and combine them in to a single view:

```bash
tl web.log*
```

In the app, press **F1** for additional help.



    
    

</details>

## History

If you [follow me](https://twitter.com/willmcgugan) on Twitter, you may have seen me refer to this app as *Tailless*, because it was intended to be a replacement for a `tail` + `less` combo.
I settled on the name "Toolong" because it is a bit more apt, and still had the same initials.

## Development

Toolong v1.0.0 has a solid feature set, which covers most of my requirements.
However, there is a tonne of features which could be added to something like this, and I will likely implement some of them in the future.

If you want to talk about Toolong, find me on the [Textualize Discord Server](https://discord.gg/Enf6Z3qhVr).


## Thanks

I am grateful for the [LogMerger](https://github.com/ptmcg/logmerger) project which I referenced (and borrowed regexes from) when building Toolong.

## Alternatives

Toolong is not the first TUI for working with log files. See [lnav](https://lnav.org/) as a more mature alternative.
