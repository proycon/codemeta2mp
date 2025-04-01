[![Project Status: WIP – Initial development is in progress, but there has not yet been a stable, usable release suitable for the public.](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip)

# Codemeta to SSHOC Open Marketplace

This is a converter to transform data from codemeta for ingestion into the [SSHOC Open Marketplace](https://github.com/SSHOC/sshoc-marketplace-backend) by communicating via their API.

## Installation

For now:

```
pip install git+https://github.com/proycon/codemeta2mp.git
```

## Usage

If you already have a `codemeta.json` file, just run `codemeta2mp --baseurl http://localhost:8080 --username Administrator --password q1w2e3r4t5 codemeta.json` to upload it to the SSHOC marketplace (the default credentials and URL are for a local development instance):

1. Find the tool you want to convert on https://tools.clariah.nl/ (e.g. https://tools.clariah.nl/frog
2. Run this on on it: ``curl --header 'Accept: application/json' https://tools.clariah.nl/frog/ | codemeta2mp --baseurl http://localhost:8080 --username Administrator --password q1w2e3r4t5 -``
