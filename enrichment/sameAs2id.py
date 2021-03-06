#!/usr/bin/python3
# -*- coding: utf-8 -*-
import elasticsearch
from elasticsearch import Elasticsearch, helpers
import json
from pprint import pprint
import argparse
import sys
import os.path
import requests
import signal
import urllib3.request
from multiprocessing import Lock, Pool, Manager
from es2json import esgenerator
from es2json import eprint
from esmarc import gnd2uri
from esmarc import isint
from esmarc import ArrayOrSingleValue
from es2json import simplebar

author_gnd_key="sameAs"
map_id={ 
    "persons": ["author","relatedTo","colleague","contributor","knows","follows","parent","sibling","spouse","children"],
    "geo":     ["deathPlace","birthPlace","workLocation","location","areaServed"],
    "orga":["copyrightHolder"],
    "tags":["mentions"],
         }
### replace SWB/GND IDs by your own IDs in your ElasticSearch Index.
### example usage: ./sameAs2swb.py -host ELASTICSEARCH_SERVER -index swbfinc -type finc -aut_index=source-schemaorg -aut_type schemaorg
def handle_author(author):
    try:
        data=es.get(index=args.aut_index,doc_type=args.aut_type,id=author,_source="@id")
    except elasticsearch.exceptions.NotFoundError:
        return None
    if "@id" in data["_source"]:
        return data["_source"]["@id"]
    
    if changed:
        es.index(index=args.index,doc_type=args.type,body=jline["_source"],id=jline["_id"])

def checkurl(gnd):
    url="https://d-nb.info/gnd/"+str(gnd)
    c = urllib3.PoolManager()
    c.request("HEAD", '')
    if c.getresponse().status == 200:
        return url
    else:
        return None

def getidbygnd(gnd,cache=None):
    if cache:
        if gnd in cache:
            return cache[gnd]
    indices=[{"index":"orga",
              "type" :"schemaorg"},
             {"index":"persons",
              "type" :"schemaorg"},
             {"index":"geo",
              "type" :"schemaorg"},
             {"index":"resources",
              "type" :"schemaorg"},
              {"index":"tags",
               "type":"schemaorg"},
             {"index":"dnb",
              "type" :"gnd",
              "index":"ef",
              "type" :"gnd"}]
    if gnd.startswith("(DE-588)"):
        uri=gnd2uri(gnd)
    elif gnd.startswith("http://d"):
        uri=gnd
    else:
        uri=checkurl(gnd)
        if not uri:
            return
    for elastic in indices:
        http = urllib3.PoolManager()
        url="http://"+args.host+":9200/"+elastic["index"]+"/"+elastic["type"]+"/_search?q=sameAs:\""+uri+"\""
        try:
                r=http.request('GET',url)
                data = json.loads(r.data.decode('utf-8'))
                if 'Error' in data or not 'hits' in data:
                    continue
        except:
            continue
        if data['hits']['total']!=1:
            continue
        for hit in data["hits"]["hits"]:
            if "_id" in hit:
                if cache:
                    cache[gnd]=str("http://data.slub-dresden.de/"+str(elastic["index"])+"/"+hit["_id"])
                    return cache[gnd]
                else:
                    return str("http://data.slub-dresden.de/"+str(elastic["index"])+"/"+hit["_id"])

def useadlookup(feld,uri,host,port,index,type,id):
        url="http://"+host+":"+str(port)+"/"+str(index)+"/"+type+"/_search?_source=@id,sameAs&q="+str(feld)+":\""+str(uri)+"\""
        r=requests.get(url,headers={'Connection':'close'})
        if r.ok:
            response=r.json().get("hits")
            if response.get("total")==1:
                return response.get("hits")[0].get("_source")
            else:
                return None
        else:
            return None

        
### avoid dublettes and nested lists when adding elements into lists
def litter(lst, elm):
    if not lst:
        lst=elm
    else:
        if isinstance(lst,str):
            lst=[lst]
        if isinstance(elm,(str,dict)):
            if elm not in lst:
                lst.append(elm)
        elif isinstance(elm,list):
            for element in elm:
                if element not in lst:
                    lst.append(element)
    return lst


def traverse(obj,path):
    if isinstance(obj,dict):
        for k,v in obj.items():
            for c,w in traverse(v,path+"."+str(k)):
                yield c,w
    elif isinstance(obj,list):
        for elem in obj:
            for c,w in traverse(elem,path+"."):
                yield c,w
    else:
        yield path,obj
        
def sameAs2ID(entity,record,host,port,index,type,id):
    changed=False
    if "sameAs" in record and isinstance(record["sameAs"],str):
        r=useadlookup("sameAs",record["sameAs"],host,port,index,type,id)
        if isinstance(r,dict) and r.get("@id"):
            changed=True
            record.pop("sameAs")
            record["@id"]=r.get("@id")
    elif "sameAs" in record and isinstance(record["sameAs"],list):
        record["@id"]=None
        for n,sameAs in enumerate(record['sameAs']):
            r=useadlookup("sameAs",sameAs,host,port,index,type,id)
            if isinstance(r,dict) and r.get("@id"):
                changed=True
                del record["sameAs"][n]
                record["@id"]=litter(record["@id"],r.get("@id"))
                for m,sameBs in enumerate(record["sameAs"]):
                    if sameBs in r.get("sameAs"):
                        del record["sameAs"][m]
        for checkfield in ["@id","sameAs"]:
            if not record[checkfield]:
                record.pop(checkfield)
    if changed:
        return record
    else:
        return None
                
def resolve(record,key,host,port,index,type,id):
    changed=False
    if index in map_id:
        for entity in map_id[index]:
            if entity in record:
                if isinstance(record[entity],list):
                    for n,sameAs in enumerate(record[entity]):
                        rec=sameAs2ID(entity,sameAs,host,port,index,type,id)
                        if rec:
                            changed=True
                            record[entity][n]=rec
                elif isinstance(record[entity],dict):
                    rec=sameAs2ID(entity,record[entity],host,port,index,type,id)
                    if rec:
                        changed=True
                        record[entity]=rec
    if changed:
        return record
    else:
        return None
        
def work(record,host,port,index,type,id,debug):
    data=resolve_uris(record.pop("_source"),host,port,index,type,id)
    if data:
        record.pop("_score")
        record["_op_type"]="index"
        record["_source"]=data
        if not args.debug:
            lock.acquire()
        actions.append(record)
        sys.stdout.write(".")
        if len(actions)>=1000:
            helpers.bulk(elastic,actions,stats_only=True)
            actions[:]=[]
        if not args.debug:
            lock.release()
            
def init(l,a,es):
    global lock
    global actions
    global elastic
    elastic=es
    actions=a
    lock = l
        
def resolve_uris(record,host,port,index,type,id):
    changed=False
    for key in map_id:
        newrecord = resolve(record,key,host,port,index,type,id)
        if newrecord:
            record=newrecord
            changed=True
    if changed:
        return record
    else:
        return None

def run(host,port,index,type,id,debug):
    es=Elasticsearch([{'host':host}],port=port)
    if id:
        record=es.get(index=index,doc_type=type,id=id).pop("_source")
        return resolve_uris(record,host,port,index,type,id)
    elif debug:
        l=[]
        a=[]
        init(l,a,es)
        for hit in esgenerator(host=host,port=port,index=index,type=type,headless=False):
            work(hit,host,port,index,type,id,debug)
        if len(a)>0:
            helpers.bulk(es,a,stats_only=True)
            a[:]=[]
    else:
        with Manager() as manager:
            a=manager.list()
            l=manager.Lock()
            with Pool(16,initializer=init,initargs=(l,a,es)) as pool:
                for hit in esgenerator(host=host,port=port,index=index,type=type,headless=False):
                    pool.apply_async(work,args=(hit,host,port,index,type,id,debug))
            if len(a)>0:
                helpers.bulk(es,a,stats_only=True)
                a[:]=[]
    
if __name__ == "__main__":
    #argstuff
    parser=argparse.ArgumentParser(description='Resolve sameAs of GND/SWB to your own IDs.')
    parser.add_argument('-host',type=str,help='hostname or IP-Address of the ElasticSearch-node to use. If None we try to read ldj from stdin.')
    parser.add_argument('-port',type=int,default=9200,help='Port of the ElasticSearch-node to use, default is 9200.')
    parser.add_argument('-type',type=str,help='ElasticSearch Index to use')
    parser.add_argument('-index',type=str,help='ElasticSearch Type to use')
    parser.add_argument('-help',action="store_true",help="print this help")
    parser.add_argument('-id',type=str,help="enrich a single id")
    parser.add_argument('-debug',action="store_true",help="disable mp for debugging purposes")
    parser.add_argument('-server',type=str,help="use http://host:port/index/type/id syntax. overwrites host/port/index/id/pretty")
    args=parser.parse_args()
    if args.server:
        slashsplit=args.server.split("/")
        args.host=slashsplit[2].rsplit(":")[0]
        if isint(args.server.split(":")[2].rsplit("/")[0]):
            args.port=args.server.split(":")[2].split("/")[0]
        args.index=args.server.split("/")[3]
        if len(slashsplit)>4:
            args.type=slashsplit[4]
        if len(slashsplit)>5:
            if "?pretty" in args.server:
                args.pretty=True
                args.id=slashsplit[5].rsplit("?")[0]
            else:
                args.id=slashsplit[5]
    if args.help:
        parser.print_help(sys.stderr)
        exit()
    run(args.host,args.port,args.index,args.type,args.id,args.debug)
