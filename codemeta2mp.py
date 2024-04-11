#!/usr/bin/env python

import sys
import argparse
import json
from rdflib import Graph, URIRef,Literal, OWL, RDF
from codemeta.common import getstream, init_graph, AttribDict, SDO, CODEMETA, REPOSTATUS, SOFTWARETYPES, TRL,  iter_ordered_list, get_doi
from codemeta.parsers.jsonld import parse_jsonld


NS_EOSC_LIFECYCLESTATUS = "https://vocabs.sshopencloud.eu/vocabularies/eosc-life-cycle-status/"
NS_EOSC_TRL = "https://vocabs.sshopencloud.eu/vocabularies/eosc-technology-readiness-level/"
NS_INVOCATION_TYPE = "https://vocabs.sshopencloud.eu/vocabularies/invocation-type/"

# Map software types from https://github.com/SoftwareUnderstanding/software_types and schema.org to https://vocabs.sshopencloud.eu/browse/invocation-type/en/page/invocationTypeScheme
SOFTWARETYPEMAP = {
    SDO.WebApplication: "webApplication",
    SOFTWARETYPES.DesktopApplication: "localApplication",
    SDO.WebAPI: "restfulWebservice", #this is a bit of a stretch as the API is not necessarily RESTful
    SOFTWARETYPES.SoftwareLibrary: "library",
    SOFTWARETYPES.CommandLineApplication: "commandLine",
    #approximate fallbacks for this that have no clear counterpart in SSHOC's vocab:
    SDO.MobileApplication: "localApplication",
    SDO.NotebookApplication: "script",
    SOFTWARETYPES.SoftwareImage: "localApplication",
    SOFTWARETYPES.SoftwarePackage: "localApplication",
    SDO.VideoGame: "localApplication",
    SOFTWARETYPES.TerminalApplication: "commandLine", #bit of a stretch, but there is no TUI equivalent
    SOFTWARETYPES.ServerApplication: "webApplication",
}

LIFECYCLEMAP = {
    #stages (coarse)
    TRL.Stage1Planning: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-preparation",
    TRL.Stage2ProofOfConcept: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-concept",
    TRL.Stage3Experimental: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-beta",
    TRL.Stage4Complete: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-production",

    #levels (more fine grained)
    TRL.Level0Idea: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-preparation",
    TRL.Level1InitialResearch: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-preparation",
    TRL.Level2ConceptFormulated: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-planned",
    TRL.Level3ProofOfConcept: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-concept",
    TRL.Level4ValidatedProofOfConcept: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-design",
    TRL.Level5EarlyPrototype: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-alpha",
    TRL.Level6LatePrototype: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-beta",
    TRL.Level7ReleaseCandidate: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-beta",
    TRL.Level8Complete: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-production",
    TRL.Level9Proven: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-production",
}

TRLMAP = {
    TRL.Level0Idea: f"{NS_EOSC_TRL}trl-1", #no level 0, group with 1
    TRL.Level1InitialResearch: f"{NS_EOSC_TRL}trl-1",
    TRL.Level2ConceptFormulated: f"{NS_EOSC_TRL}trl-2",
    TRL.Level3ProofOfConcept: f"{NS_EOSC_TRL}trl-3",
    TRL.Level4ValidatedProofOfConcept: f"{NS_EOSC_TRL}trl-4",
    TRL.Level5EarlyPrototype: f"{NS_EOSC_TRL}trl-5",
    TRL.Level6LatePrototype: f"{NS_EOSC_TRL}trl-6",
    TRL.Level7ReleaseCandidate: f"{NS_EOSC_TRL}trl-7",
    TRL.Level8Complete: f"{NS_EOSC_TRL}trl-8",
    TRL.Level9Proven: f"{NS_EOSC_TRL}trl-9"
}

#takes precendence over all others
REPOSTATUSMAP_PRIO = {
    REPOSTATUS.abandoned: f"{NS_EOSC_LIFECYCLESTATUS}/life_cycle_status-termination",
}

#fallback only if no others match
REPOSTATUSMAP_FALLBACK = {
    REPOSTATUS.wip: f"{NS_EOSC_LIFECYCLESTATUS}life_cycle_status-concept",
}

def clean(d: dict) -> dict:
   return { k: v for k,v in d.items() if v }

def get_actors(g: Graph, res: URIRef, prop=SDO.author, offset=0):
    if prop == SDO.author:
        code = "author"
        label = "Author"
    elif prop == SDO.maintainer:
        code = "maintainer"
        label = "Maintainer"
    elif prop == SDO.contributor:
        code = "contributor"
        label = "Contributor"
    else:
        raise Exception("Unknown property: " + str(prop))

    for i,(_,_,o) in enumerate(iter_ordered_list(g,res,prop)):
        if isinstance(o, Literal):
            yield clean({
                "actor": {
                    "name": str(o)
                },
                "role": { 
                    "code": code,
                    "label": label,
                    "ord": offset+i+1,
                }
            })
        else:
            external_ids = []
            external_id = None
            if str(o).startswith("https://orcid.org/"):
                external_id = str(o)
            elif g.value(o,OWL.sameAs,None) and str(g.value(o,OWL.sameAs,None)).startswith("https://orcid.org/"):
                external_id = str(g.value(o,OWL.sameAs,None))
            if external_id:
                external_ids.append({
                    "identifierService": {
                        "code": "ORCID",
                        "label": "ORCID",
                        "urlTemplate": "https://orcid.org/{source-item-id}",
                    },
                    "identifier": external_id.replace("https://orcid.org/","")
                })
            name = None
            if isinstance(o, Literal):
                name = str(o)
            elif (o,SDO.name,None) in g:
                name = g.value(o, SDO.name,None)
            elif (o,SDO.givenName,None) in g and (o,SDO.familyName,None) in g:
                name = str(g.value(o, SDO.givenName,None)) + " " + str(g.value(o, SDO.familyName,None))
            url = g.value(o, SDO.url,None)
            yield clean({
                "actor": {
                    "name": name,
                    "externalIds": external_ids,
                    "website": str(url) if url else None
                },
                "role": { 
                    "code": code,
                    "label": label,
                    "ord": offset+i+1,
                }
            })



if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="codemeta2mp", description="Converts codemeta to SSHOC Open Marketplace") 
    parser.add_argument('inputfiles', nargs='+', help="Input files (JSON-LD)", type=str) 

    args = parser.parse_args()
    attribs = AttribDict({})

    entries = []
    for filename in args.inputfiles:
        g, contextgraph = init_graph(attribs)
        parse_jsonld(g, None, getstream(filename), attribs)

        for res,_,_ in g.triples((None,RDF.type, SDO.SoftwareSourceCode)):
            assert isinstance(res, URIRef)
            actors = list(get_actors(g, res, SDO.maintainer))
            actors += list(get_actors(g, res, SDO.author, len(actors)))
            properties = []
            for _,_, license in g.triples((res, SDO.license, None)):
                if str(license).startswith("http"):
                    properties.append({
                        "type": {
                            "code": "license",
                        },
                        "concept": {
                            "code": str(license).strip("/").split("/")[-1],
                            "uri": str(license),
                        }
                    })
            for _,_, category in g.triples((res, SDO.applicationCategory, None)):
                if str(category).startswith("https://vocabs.dariah.eu/tadirah/"):
                    properties.append({
                        "type": {
                            "code": "activity",
                        },
                        "concept": {
                            "code": str(category).strip("/").split("/")[-1],
                            "uri": str(category),
                        }
                    })
            external_ids = []
            external_id = str(res)
            if external_id.startswith("https://tools.clariah.nl/"):
                external_ids.append({
                    "identifierService": {
                        "code": "CLARIAH-NL",
                        "label": "CLARIAH Tools",
                        "urlTemplate": "https://tools.clariah.nl/{source-item-id}",
                    },
                    "identifier": external_id.replace("https://tools.clariah.nl/","")
                })
            else:
                external_ids.append(external_id)
            doi = get_doi(g, res)
            if doi:
                external_ids.append({
                    "identifierService": {
                        "code": "DOI",
                        "label": "DOI",
                        "urlTemplate": "https://doi.org/{source-item-id}",
                    },
                    "identifier": doi
                })

            accessible_at = []
            modes_of_use = set()
            for _,_,targetproduct in g.triples((res,SDO.targetProduct,None)):
                url = g.value(targetproduct,SDO.url,None)
                if url:
                    accessible_at.append(str(url))
                for _,_,interfacetype in g.triples((targetproduct, RDF.type,None)):
                    if str(interfacetype).startswith(NS_INVOCATION_TYPE):
                        #already in the right vocabulary, no mapping needed
                        modes_of_use.add(interfacetype)
                    elif interfacetype in SOFTWARETYPEMAP:
                        modes_of_use.add(SOFTWARETYPEMAP[interfacetype])
                    else:
                        print("WARNING: Unknown targetProduct type (can't map):", interfacetype,file=sys.stderr)
            for mode_of_use in modes_of_use:
                properties.append(
                    {
                        "type": {
                            "code": "mode-of-use"
                        },
                        "concept": {
                            "code": mode_of_use,
                            "uri": f"{NS_INVOCATION_TYPE}{mode_of_use}"
                        }
                    }
                )
            lifecycle_status = None
            trl = None
            for _,_,devstatus in g.triples((res,CODEMETA.developmentStatus,None)):
                if str(devstatus).startswith(NS_EOSC_LIFECYCLESTATUS):
                    #already in the right vocabulary, no mapping needed
                    lifecycle_status = str(devstatus)
                if devstatus in REPOSTATUSMAP_PRIO:
                    lifecycle_status = REPOSTATUSMAP_PRIO[devstatus]
                if str(devstatus).startswith(NS_EOSC_TRL):
                    #already in the right vocabulary, no mapping needed
                    trl = str(devstatus)
                if devstatus in TRLMAP:
                    trl = TRLMAP[devstatus]
            if not lifecycle_status:
                for _,_,devstatus in g.triples((res,CODEMETA.developmentStatus,None)):
                    if devstatus in LIFECYCLEMAP:
                        lifecycle_status = LIFECYCLEMAP[devstatus]
            if not lifecycle_status:
                for _,_,devstatus in g.triples((res,CODEMETA.developmentStatus,None)):
                    if devstatus in REPOSTATUSMAP_FALLBACK:
                        lifecycle_status = REPOSTATUSMAP_FALLBACK[devstatus]
            if lifecycle_status:
                properties.append(
                    {
                        "type": {
                            "code": "life-cycle-status"
                        },
                        "concept": {
                            "code": str(lifecycle_status).split("/")[-1],
                            "uri": str(lifecycle_status)
                        }
                    }
                )
            if trl:
                properties.append(
                    {
                        "type": {
                            "code": "technology-readiness-level"
                        },
                        "concept": {
                            "code": trl.split("/")[-1],
                            "uri": trl
                        }
                    }
                )

            for _,_,keyword in g.triples((res,SDO.keywords,None)):
                if isinstance(keyword, Literal):
                    properties.append(
                        {
                            "type": {
                                "code": "keyword"
                            },
                            "concept": {
                                "code": str(keyword.lower().replace(" ","+")),
                                "label": str(keyword),
                            }
                        }
                    )

            sourcerepo = g.value(res,SDO.codeRepository,None)
            if sourcerepo:
                if not accessible_at:
                    accessible_at = [ str(sourcerepo) ] #fallback
                if str(sourcerepo).startswith("https://github.com/"):
                    external_ids.append({
                        "identifierService": {
                            "code": "GitHub",
                            "label": "GitHub",
                            "urlTemplate": "https://github.com/{source-item-id}",
                        },
                        "identifier": str(sourcerepo).replace("https://github.com/","")
                    })
                elif str(sourcerepo).startswith("https://gitlab.com/"):
                    external_ids.append({
                        "identifierService": {
                            "code": "GitLab",
                            "label": "GitLab",
                            "urlTemplate": "https://gitlab.com/{source-item-id}",
                        },
                        "identifier": str(sourcerepo).replace("https://gitlab.com/","")
                    })
                elif str(sourcerepo).startswith("https://bitbucket.org/"):
                    external_ids.append({
                        "identifierService": {
                            "code": "Bitbucket",
                            "label": "Bitbucket",
                            "urlTemplate": "https://bitbucket.org/{source-item-id}",
                        },
                        "identifier": str(sourcerepo).replace("https://bitbucket.org/","")
                    })
                elif str(sourcerepo).startswith("https://codeberg.org/"):
                    external_ids.append({
                        "identifierService": {
                            "code": "Codeberg",
                            "label": "Codeberg",
                            "urlTemplate": "https://codeberg.org/{source-item-id}",
                        },
                        "identifier": str(sourcerepo).replace("https://codeberg.org/","")
                    })
                elif str(sourcerepo).startswith("https://git.sr.ht/"):
                    external_ids.append({
                        "identifierService": {
                            "code": "sourcehut",
                            "label": "sourcehut",
                            "urlTemplate": "https://git.sr.ht/{source-item-id}",
                        },
                        "identifier": str(sourcerepo).replace("https://git.sr.ht/","")
                    })

            if g.value(res, SDO.version, None):
                properties.append(
                    {
                        "type": {
                            "code": "version"
                        },
                        "value": str(g.value(res,SDO.version,None)),
                    }
                )

            for _,_,o in g.triples((res, SDO.softwareHelp,None)): 
                url = None
                if isinstance(o, Literal) and str(o).startswith("http"):
                    url = str(o)
                elif isinstance(g.value(o,SDO.url,None), Literal):
                    url = str(g.value(o,SDO.url,None))
                if url:
                    properties.append(
                        {
                            "type": {
                                "code": "user-manual-url"
                            },
                            "value": url,
                        }
                    )

            #a bit of a crude search for possible languages (should usually occur in a consumesData,producesData context)
            languages = set()
            for _,_,o in g.triples((None, SDO.inLanguage,None)): 
                if str(o).startswith("https://vocabs.acdh.oeaw.ac.at/iso6393/") or str(o).startswith("https://iso639-3.sil.org/code/"):
                    languages.add(str(o).split("/")[-1])
            for language in languages:
                properties.append(
                    {
                        "type": {
                            "code": "language"
                        },
                        "concept": {
                            "code": language,
                            "uri": f"https://vocabs.acdh.oeaw.ac.at/iso6393/{language}"
                        }
                    }
                )


            entry = {
                "label": g.value(res, SDO.name, None),
                "description": g.value(res, SDO.description, None),
                "externalID": external_ids, 
                "accessibleAt": accessible_at,
                "thumbnail": g.value(res,SDO.thumbnailUrl,None),
                "contributors": actors,
                "properties": properties,
            }
            json.dump(clean(entry), sys.stdout)