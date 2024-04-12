[![Project Status: WIP – Initial development is in progress, but there has not yet been a stable, usable release suitable for the public.](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip)

# Codemeta to SSHOC Open Marketplace

This is a converter to transform data from codemeta into a representation that can be submitted to the SSHOC Open Marketplace via an API.

## Installation

For now:

```
pip install git+https://github.com/proycon/codemeta2mp.git
```

## Usage

If you already have a `codemeta.json` file, just run `codemeta2mp codemeta.json` to get the SSHOC Open Marketplace representation. Otherwise:

1. Find the tool you want to convert on https://tools.clariah.nl/ (e.g. https://tools.clariah.nl/frog
2. Run this on on it: ``curl --header 'Accept: application/json' https://tools.clariah.nl/frog/ | codemeta2mp -`` to get the SSHOC Open Marketplace representation, optionally pipe through ``jq`` for pretty output.



