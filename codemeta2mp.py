#!/usr/bin/env python

import sys
import argparse
import json
import requests
from typing import Optional, List, Union
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

# from @mkrzmr: You can pass empty values as you need to, the API will just ignore it
EMPTY_PROPERTY_CONCEPT = {
    "code": "",
    "vocabulary": {
        "code": "",
    },
    "uri": "",
}

class MarketPlaceAPI:
    def __init__(self, baseurl: str, username: Optional[str] = None, password: Optional[str] = None, token_secret: Optional[str] =None, debug=False):
        """Initialize a client connection to the Marketplace API, username and password are required for write access"""
        self.debug = debug
        self.baseurl = baseurl
        if self.baseurl[-1] == "/":
            self.baseurl = self.baseurl[:-1]
        if username and password:
            #required for write-access
            url= f"{self.baseurl}/api/auth/sign-in"
            response = requests.post(url, headers={'Content-type': 'application/json'}, json={'username' : username,'password': password})
            response.raise_for_status()
            self.bearer= response.headers['Authorization'] #this includes the bearer prefix
            if self.debug:
                print(f"Sign-in succesful: {self.bearer}", file=sys.stderr)
        elif token_secret:
            self.bearer = token_secret
        else:
            self.bearer = None

    def headers(self, **kwargs) -> dict:
        """Internal helper method to return common HTTP request headers"""
        headers= {'Content-type': 'application/json', 'Accept': "application/json"}
        if self.bearer:
            headers['Authorization'] = f"{self.bearer}" #includes bearer prefix
            if self.debug:
                print(f"Passing authorization: {self.bearer}", file=sys.stderr)
        for key, value in kwargs.items():
            key = key[0].upper() + key[1:].replace("_","-")
            headers[key] = value
        return headers

    def get_source(self, url: str) -> dict:
        """Get a source by URL"""
        response = requests.get(f"{self.baseurl}/api/sources", params={"q": url },headers=self.headers())
        self.validate_response(response,None,"get_source")
        if response.json()['hits'] == 0:
            raise KeyError()
        return response.json()['sources'][0]

    def get_or_add_source(self, label: str, url: str, urltemplate: str) -> dict:
        """Get a source by URL, or adds it anew if it doesn't exist yet"""
        try:
            return self.get_source(url)
        except (requests.exceptions.HTTPError, KeyError):
            return self.add_source(label, url, urltemplate)
        except requests.exceptions.JSONDecodeError:
            raise

    def add_source(self, label: str, url: str, urltemplate: str) -> dict:
        """Adds a source"""
        payload = {
            "label": label,
            "url": url,
            "urlTemplate": urltemplate,
        }
        response = requests.post(f"{self.baseurl}/api/sources", headers=self.headers(), json=payload)
        self.validate_response(response,payload,"add_source")
        return response.json()['sources'][0]

    def get_actor(self, name: str) -> dict:
        """Gets an actor by name"""
        response = requests.get(f"{self.baseurl}/api/actor-search", params={"q": name.strip() },headers=self.headers())
        self.validate_response(response,None,"get_actor")
        if response.json()['hits'] == 0:
            raise KeyError()
        return response.json()['actors'][0] #returns the first match! (may not be what you want if there are multiple)

    def add_actor(self, name: str,  website: Optional[str], email: Optional[str], orcid: Optional[str]) -> dict:
        """Adds an actor"""
        external_ids = []
        if orcid:
            external_ids.append({
                "identifierService": {
                    "code": "ORCID",
                    "label": "ORCID",
                    "urlTemplate": "https://orcid.org/{source-item-id}",
                },
                "identifier": orcid.replace("https://orcid.org/","")
            })
        payload = {
            "name": name,
            "externalIds": external_ids,
            "website": website if website else "",
            "email": email if email else "",
            "affiliations": [], # we don't do affiliations in this convertor yet (too messy with changing affiliations and duplicates)
        }
        response = requests.post(f"{self.baseurl}/api/actors", headers=self.headers(), json=payload)
        self.validate_response(response,payload,"add_actor")
        return response.json()

    def get_or_add_actor(self, name: str,  website: Optional[str], email: Optional[str], orcid: Optional[str]) -> dict:
        """Gets an actor by name, or adds it if it doesn't exist yet"""
        try:
            return self.get_actor(name)
        except (requests.exceptions.HTTPError, KeyError):
            return self.add_actor(name, website, email, orcid )
        except requests.exceptions.JSONDecodeError:
            raise

    def get_tool(self, name: str, sourcelabel: str = "") -> Optional[dict]:
        """Gets the data of tool if it exists"""
        response = requests.get(f"{self.baseurl}/api/item-search", params={"q": name.strip(), "f": f"f.source={sourcelabel}","categories":"tool-or-service"},headers={'accept': 'application/json'})
        self.validate_response(response,None,"get_tool")
        if response.json()['hits'] == 0:
            return None
        elif response.json()['hits'] > 1:
            #multiple hits, refuse
            return None
        return response.json()['items'][0] #grab first match, this may not be accurate

    def add_tool(self, data: dict):
        """Adds a tool, given a full data object"""
        response = requests.post(f"{self.baseurl}/api/tools-services", headers=self.headers(), json=data)
        self.validate_response(response, data, "add_tool")

    def update_tool(self, persistent_id: str, data: dict):
        """Updates an existing tool, given a full data object"""
        response = requests.post(f"{self.baseurl}/api/tools-services/" + persistent_id, headers=self.headers(), json=data)
        self.validate_response(response, data, "update_tool")

    def validate_response(self, response: requests.Response, data: Union[dict,None], context: str):
        """Internal helper method to validate responses and raise errors if needed"""
        if response.status_code < 200 or response.status_code >= 300:
            print(f"-------- ERROR {response.status_code} in {context} ---------",file=sys.stderr)
            if data:
                print("POSTED DATA:",file=sys.stderr)
                print(json.dumps(data,indent=4),file=sys.stderr)
            if response.json():
                print("ERROR FEEDBACK:",file=sys.stderr)
                print(json.dumps(response.json(),indent=4), file=sys.stderr)
            response.raise_for_status()
        elif self.debug:
            print(f"[DEBUG {context}]:", response.json(),file=sys.stderr)

        

def clean(d: dict) -> dict:
   """Removes keys/values with empty values"""
   return { k: v for k,v in d.items() if v }

def get_actors(api: MarketPlaceAPI, g: Graph, res: URIRef, prop=SDO.author, offset=0):
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
                "actor": api.get_or_add_actor(str(o),None,None,None),
                "role": { 
                    "code": code,
                    "label": label,
                    "ord": offset+i+1,
                }
            })
        else:
            orcid = None
            if str(o).startswith("https://orcid.org/"):
                orcid = str(o)
            elif g.value(o,OWL.sameAs,None) and str(g.value(o,OWL.sameAs,None)).startswith("https://orcid.org/"):
                orcid = str(g.value(o,OWL.sameAs,None))
            if isinstance(o, Literal):
                name = str(o)
            elif (o,SDO.name,None) in g:
                name = g.value(o, SDO.name,None)
            elif (o,SDO.givenName,None) in g and (o,SDO.familyName,None) in g:
                name = str(g.value(o, SDO.givenName,None)) + " " + str(g.value(o, SDO.familyName,None))
            else:
                raise Exception("No name found for actor")
            url = g.value(o, SDO.url,None)
            email = g.value(o, SDO.email,None)
            yield clean({
                "actor": api.get_or_add_actor(name, url, email, orcid),
                "role": { 
                    "code": code,
                    "label": label,
                    "ord": offset+i+1,
                }
            })



def main():
    parser = argparse.ArgumentParser(prog="codemeta2mp", description="Converts codemeta to SSHOC Open Marketplace") 
    parser.add_argument('--baseurl', help="Marketplace API base url", type=str, default="https://marketplace-api.sshopencloud.eu") 
    parser.add_argument('--username', help="Username", type=str, required=False) 
    parser.add_argument('--password', help="Password", type=str, required=False) 
    parser.add_argument('--token', help="Token secret", type=str, required=False) 
    parser.add_argument('--sourcelabel', help="Source label", type=str, default="CLARIAH-NL Tools") 
    parser.add_argument('--sourceurl', help="Source URL", type=str, default="https://tools.clariah.nl") 
    parser.add_argument('--sourcetemplate', help="Source URL Template", type=str, default="https://tools.clariah.nl/{source-item-id}") 
    parser.add_argument('--debug',help="Debug mode", action="store_true")
    parser.add_argument('inputfiles', nargs='+', help="Input files (JSON-LD)", type=str) 

    args = parser.parse_args()
    attribs = AttribDict({})

    api = MarketPlaceAPI(args.baseurl, args.username, args.password, args.token, args.debug) 
    source = api.get_or_add_source(args.sourcelabel, args.sourceurl, args.sourcetemplate)

    for filename in args.inputfiles:
        g, _ = init_graph(attribs)
        parse_jsonld(g, None, getstream(filename), attribs)

        for res,_,_ in g.triples((None,RDF.type, SDO.SoftwareSourceCode)):
            assert isinstance(res, URIRef)
            actors = list(get_actors(api, g, res, SDO.maintainer))
            actors += list(get_actors(api, g, res, SDO.author, len(actors)))
            properties = []
            for _,_, license in g.triples((res, SDO.license, None)):
                if str(license).startswith("http"):
                    properties.append({
                        "type": {
                            "code": "license",
                        },
                        "concept": {
                            "code": str(license).strip("/").split("/")[-1],
                            "vocabulary": {
                                "code": "software-license"
                            },
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
                            "vocabulary": {
                                "code": "tadirah2"
                            },
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
                            "vocabulary": {
                                "code": "invocation-type",
                            },
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
                            "vocabulary": {
                                "code": "life-cycle-status" #MAYBE TODO: verify?
                            },
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
                            "vocabulary": {
                                "code": "technology-readiness-level" #MAYBE TODO: verify? 
                            },
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
                                "code": str(keyword.strip().lower().replace(" ","+")),
                                "label": str(keyword.strip()),
                                "vocabulary": {
                                    "code": "sshoc-keyword",
                                }
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
                        "concept": EMPTY_PROPERTY_CONCEPT,
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
                            "concept": EMPTY_PROPERTY_CONCEPT,
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
                            "vocabulary": {
                                "code": "iso-639-3"
                            },
                            "uri": f"https://vocabs.acdh.oeaw.ac.at/iso6393/{language}"
                        }
                    }
                )


            entry = {
                "label": g.value(res, SDO.name, None),
                "description": g.value(res, SDO.description, None),
                "externalID": external_ids, 
                "accessibleAt": accessible_at,
                "source": source,
                "sourceItemId": g.value(res, SDO.identifier, None),
                "thumbnail": g.value(res,SDO.thumbnailUrl,None),
                "contributors": actors,
                "properties": properties,
            }

            entry = { k:v for k, v in entry.items() if v }

            existing = api.get_tool(g.value(res, SDO.name, None))
            if existing:
                persistent_id = existing['persistentId']
                lastupdate_mp = existing['lastInfoUpdate']
                lastmodified_upstream = g.value(res, SDO.dateModified, None)
                needs_update = False
                if lastmodified_upstream:
                    if lastmodified_upstream > lastupdate_mp: #lexographic comparison should work
                        needs_update = True
                if needs_update:
                    api.update_tool(persistent_id, entry)
                else:
                    print("Already exists and no update needed",file=sys.stderr)
            else:
                api.add_tool(entry)

            #json.dump(entry, sys.stdout)

if __name__ == "__main__":
    main()
