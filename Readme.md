# Enzi

## Introduction

Enzi(Enzyme IC) is a tool for automating HDL project. Currently, this package is in its early stage. It use an toml configuration file (Enzi.toml) to maintain HDL project, see ExampleEnzi.toml for details. 

## Quick Start

install the tool:

```bash
# normal setup
sudo python3 setup.py
# or development setup
sudo python3 setup.py develop
```

uninstall the tool:

```bash
# normal uninstall
sudo python3 setup.py
# if previous steup via develop arg
sudo python3 setup.py develop --uninstall
```

This tool will automating fetch the Enzi.toml (or specified toml file) in the given root directory.

Usage help:
```bash

enzi -h

usage: enzi [-h] [--root ROOT] [--silence-mode] [--config CONFIG]
            {build,run,sim,program_device} ...

positional arguments:
  {build,run,sim,program_device}
    build               build the given project
    run                 run the given project
    sim                 simulate the given project
    program_device      program the given project to device

optional arguments:
  -h, --help            show this help message and exit
  --root ROOT           Enzi project root directory
  --silence-mode        only capture stderr
  --config CONFIG       Specify the Enzi.toml file to use
```
