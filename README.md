[![Project Status: Active -- The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![Latest release in the Python Package Index](https://img.shields.io/pypi/v/codemeta2mp)](https://pypi.org/project/codemeta2mp/)

# Codemeta to SSHOC Open Marketplace

This is a converter to transform data from codemeta (as used by <https://tools.clariah.nl>) for ingestion into the [SSHOC Open Marketplace](https://github.com/SSHOC/sshoc-marketplace-backend) by communicating via their API.

## Installation

Run (preferably in a Python virtual environment):

```
pip install codemeta2mp
```

## Usage

If you already have a `codemeta.json` file, just run `codemeta2mp --baseurl http://localhost:8080 --username Administrator --password q1w2e3r4t5 codemeta.json` to upload it to the SSHOC marketplace (the default credentials and URL are for a local development instance):

1. Find the tool you want to convert on https://tools.clariah.nl/ (e.g. https://tools.clariah.nl/frog
2. Run this on on it: ``curl --header 'Accept: application/json' https://tools.clariah.nl/frog/ | codemeta2mp --baseurl http://localhost:8080 --username Administrator --password q1w2e3r4t5 -``

## Considerations & Discussion

A conversion from one vocabulary to another always presents some challenges, as
terms do not always map exactly one to one. Some decisions and assumptions have to be
made by the converter.

The following were made for the conversion from codemeta (as used by the CLARIAH-NL Tools) to the sshoc open marketplace.
If any of the SSHOC/EOSC SKOS terms are used directly in the codemeta, then they will of course be preserved as-is.

* [SSHOC Invocation Type](https://vocabs.sshopencloud.eu/browse/invocation-type/en/page/invocationTypeScheme) does not cover all we have in our [Software Types](https://github.com/SoftwareUnderstanding/software_types), some mappings are sub-optimal.
* [EOSC Resource Technology readiness levels](https://vocabs.sshopencloud.eu/browse/eosc-technology-readiness-level/en/) go from 1-9, [CLARIAH's](https://github.com/CLARIAH/tool-discovery/blob/master/schemas/research-technology-readiness-levels.jsonld) go from 0-9. We map both our 0 and 1 to their 1.
* [EOSC Lifecycle status](https://vocabs.sshopencloud.eu/browse/eosc-life-cycle-status/en/) values we derive from our use of [Repostatus](https://www.repostatus.org/) for `codemeta:developmentStatus` (to indicate maintenance status) and TRL.
* `codemeta:issueTracker` gets mapped to SSHOC Marketplace's `helpdesk-url`
* Software as a Service by definition has at least two `accessible_at` URLs after conversion. One pointing to the source code, and one to the service. The marketplace doesn't really have the mechanism for fine-grained control to distinguish the two yet keep the strong relation.
* We both use Tadirah for `schema:applicationCategory` aka `activity`. This maps one-to-one.
* Marketplace has an Austrian bias and uses [ÖFOS 2012. Österreichische Version der 'Fields of Science and Technology (FOS) Classification'](https://vocabs.acdh.oeaw.ac.at/oefos/de/page/Schema) for `discipline` whereas CLARIAH-NL has a dutch bias and uses [NWO's classification](https://github.com/CLARIAH/tool-discovery/blob/master/schemas/nwo-research-fields.jsonld) (in `schema:applicationCategory`. A conversion for this still needs to be established.



