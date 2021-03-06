#!/usr/bin/python3
# -*- coding: utf-8 -*-
from datetime import datetime
import json
from pprint import pprint
import elasticsearch
import argparse
import sys, os, time, atexit
from signal import SIGTERM 

class Daemon:
    """
    A generic daemon class.
    
    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced 
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit first parent
                sys.exit(0) 
        except OSError as e: 
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/") 
        os.setsid() 
        os.umask(0) 

        # do second fork
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit from second parent
                sys.exit(0) 
        except OSError as e: 
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1) 
    
        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(self.stdin, 'r')
        so = open(self.stdout, 'a+')
        se = open(self.stderr, 'a+')
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        with open(self.pidfile,'w+') as pf:
            pf.write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            with open(self.pidfile,'r') as pf:
                pid = int(pf.read().strip())
                if pid:
                    message = "pidfile %s already exist. Daemon already running?\n"
                    sys.stderr.write(message % self.pidfile)
                    sys.exit(1)
        except IOError:
            pid = None
        # Start the daemon
        self.daemonize()
        self.run()

    def stop(self):
        """
        Stop the daemon
        """
        # Get the pid from the pidfile
        try:
            with open(self.pidfile,'r') as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart

        # Try killing the daemon process	
        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print(str(err))
                sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """


class simplebar():
    count=0
    def __init__(self):
        self.count=0
        
    def reset(self):
        self.count=0
        
    def update(self,num=None):
        if num:
            self.count+=num
        else:
            self.count+=1
        sys.stderr.write(str(self.count)+"\n"+"\033[F")
        sys.stderr.flush()
        
def ArrayOrSingleValue(array):
    if array:
        length=len(array)
        if length>1 or isinstance(array,dict):
            return array
        elif length==1:
            for elem in array:
                 return elem
        elif length==0:
            return None
        
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)   
    
    
def esfatgenerator(host=None,port=9200,index=None,type=None,body=None,source=True,source_exclude=None,source_include=None):
    if not source:
        source=True
    es=elasticsearch.Elasticsearch([{'host':host}],port=port)
    try:
        page = es.search(
            index = index,
            doc_type = type,
            scroll = '12h',
            size = 1000,
            body = body,
            _source=source,
            _source_exclude=source_exclude,
            _source_include=source_include)
    except elasticsearch.exceptions.NotFoundError:
        sys.stderr.write("aborting.\n")
        exit(-1)
    sid = page['_scroll_id']
    scroll_size = page['hits']['total']
    yield page.get('hits').get('hits')
    while (scroll_size > 0):
        pages = es.scroll(scroll_id = sid, scroll='12h')
        sid = pages['_scroll_id']
        scroll_size = len(pages['hits']['hits'])
        yield pages.get('hits').get('hits')
        
    ### avoid dublettes and nested lists when adding elements into lists
def litter(lst, elm):
    if not lst:
        return elm
    else:
        if isinstance(elm,str):
            if elm not in lst:
                if isinstance(lst,str):
                    return [lst,elm]
                elif isinstance(lst,list):
                    lst.append(elm)
                    return lst
        elif isinstance(elm,list):
            if isinstance(lst,str):
                lst=[lst]
            if isinstance(lst,list):
                for element in elm:
                    if element not in lst:
                        lst.append(element)
            return lst
        else:
            return lst

def esgenerator(host=None,port=9200,index=None,type=None,body=None,source=True,source_exclude=None,source_include=None,headless=False):
    if not source:
        source=True
    es=elasticsearch.Elasticsearch([{'host':host}],port=port)
    try:
        page = es.search(
            index = index,
            doc_type = type,
            scroll = '12h',
            size = 1000,
            body = body,
            _source=source,
            _source_exclude=source_exclude,
            _source_include=source_include)
    except elasticsearch.exceptions.NotFoundError:
        sys.stderr.write("not found: "+host+":"+port+"/"+index+"/"+type+"/_search\n")
        exit(-1)
    sid = page['_scroll_id']
    scroll_size = page['hits']['total']
    for hits in page['hits']['hits']:
        if headless:
            yield hits['_source']
        else:
            yield hits
    while (scroll_size > 0):
        pages = es.scroll(scroll_id = sid, scroll='12h')
        sid = pages['_scroll_id']
        scroll_size = len(pages['hits']['hits'])
        for hits in pages['hits']['hits']:
            if headless:
                yield hits['_source']
            else:
                yield hits

def isint(num):
    try: 
        int(num)
        return True
    except ValueError:
        return False
    
if __name__ == "__main__":
    parser=argparse.ArgumentParser(description='simple ES.Getter!')
    parser.add_argument('-host',type=str,default="127.0.0.1",help='hostname or IP-Address of the ElasticSearch-node to use, default is localhost.')
    parser.add_argument('-port',type=int,default=9200,help='Port of the ElasticSearch-node to use, default is 9200.')
    parser.add_argument('-index',type=str,help='ElasticSearch Search Index to use')
    parser.add_argument('-type',type=str,help='ElasticSearch Search Index Type to use')
    parser.add_argument('-source',type=str,help='just return this field(s)')
    parser.add_argument("-include",type=str,help="include following _source field(s)")
    parser.add_argument("-exclude",type=str,help="exclude following _source field(s)")
    parser.add_argument("-id",type=str,help="retrieve single document (optional)")
    parser.add_argument("-headless",action="store_true",default=False,help="don't include Elasticsearch Metafields")
    parser.add_argument('-body',type=str,help='Searchbody')
    parser.add_argument('-server',type=str,help="use http://host:port/index/type/id?pretty. overwrites host/port/index/id/pretty") #no, i don't steal the syntax from esbulk...
    parser.add_argument('-pretty',action="store_true",default=False,help="prettyprint")
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
    if args.pretty:
        tabbing=4
    else:
        tabbing=None
    if not args.id:
        for json_record in esgenerator(host=args.host,port=args.port,index=args.index,type=args.type,body=args.body,source=args.source,headless=args.headless,source_exclude=args.exclude,source_include=args.include):
            sys.stdout.write(json.dumps(json_record,indent=tabbing)+"\n")
    else:
        es=elasticsearch.Elasticsearch([{"host":args.host}],port=args.port)
        json_record=None
        if not args.headless:
            json_record=es.get(index=args.index,doc_type=args.type,_source=True,_source_exclude=args.exclude,_source_include=args.include,id=args.id)
        else:
            json_record=es.get_source(index=args.index,doc_type=args.type,_source=True,_source_exclude=args.exclude,_source_include=args.include,id=args.id)
        if json_record:
            sys.stdout.write(json.dumps(json_record,indent=tabbing)+"\n")
            
                
