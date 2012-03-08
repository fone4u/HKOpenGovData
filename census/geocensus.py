#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import pg
import re
import csv
import types
import getopt
#import datetime
import kmlbase
import kmldom
import kmlengine
import kmlcedric
import mypass

class GeoCensus():
    """Generates KML based on Census Geo and Data"""

    pgconn = None
    GCHARTURL = "http://chart.apis.google.com/chart"
    GEO_AVAIL = ["coast", "dc", "dc_land", "dcca", "tpu_small", "tpu_large", "tpu", "tpusb_small", "dist_nt"]
    GEO_KEYS = {"dc_land2": "dc"}

    def __init__(self, geo=None):
	self.pgconn = mypass.getConn()
	if geo is None:
	    self.key = None
	    self.geotable = None
	else:
	    self.geotable = geo
    	    if geo in self.GEO_KEYS:
    		self.key = self.GEO_KEYS[geo]
    	    else:
    		self.key = geo
	self.geokml = dict()
	self.data = dict()
	self.factory = kmldom.KmlFactory_GetFactory()
	self.kml = self.factory.CreateElementById(kmldom.Type_kml)
	self.geo = None
	self.geo_tolerance = None
	self.output = None
	self.verbose = False
	self.outputformat = "csv"

    def usage(self):
	print "geocensus.py [-c(csv)|-d(data)|-h(help)|-k(kml)|-o(output_file)|-v(verbose)]"

    def setGeo(self, geo):
	if self.geotable is None:
	    self.geotable = geo
	if self.key is None:
	    if geo in self.GEO_KEYS:
		self.key = self.GEO_KEYS[geo]
	    else:
		self.key = geo

    def setGeoTolerance(self, tolerance):
	self.geo_tolerance = str(tolerance)

    def geodb(self):
	if self.geotable is None:
	    return 0
	if self.geo_tolerance is not None:
	    the_geom = "ST_SimplifyPreserveTopology(the_geom,%(tolerance)s)" % { "tolerance": self.geo_tolerance }
	else:
	    the_geom = "the_geom"
	sql_args = { "table_name": "hkcensus." + self.geotable, "orderby": self.key, "key": self.key, "the_geom": the_geom }
	sql = "SELECT %(key)s, ST_AsKML(%(the_geom)s) boundary, ST_AsKML(ST_Centroid(the_geom)) point FROM %(table_name)s ORDER BY %(orderby)s "
	if self.verbose:
	    print sql % sql_args
	resgeo = self.pgconn.query(sql % sql_args).dictresult()
	for x in resgeo:
	    self.geokml[x[self.key]] = x

    def getCensusData(self, datatable_name, keys=list()):
	sql_args = { "table_name": "hkcensus." + datatable_name, "in": "", "orderby": self.key, "key": self.key }
	keys_str = list()
	for k in keys:
	    keys_str.append(str(k))
	if len(keys) > 0 and len(primary_key) > 0:
	    sql_args["in"] = " WHERE %(key)s IN (%(ids)s) " % { "key": self.key, "ids": ",".join(keys_str) }
	sql = "SELECT * FROM %(table_name)s %(in)s ORDER BY %(orderby)s "
	resdata = self.pgconn.query(sql % sql_args).dictresult()
	print sql % sql_args
	for x in resdata:
	    self.data[x[self.key]] = x

    def genCsv(self):
	if self.verbose:
	    print "generating CSV..."
	#req.content_type = "application/vnd.ms-excel"
	cols = [self.key]
	if len(self.data) > 0:
	    datacols = self.data[self.data.keys()[0]].keys()
	    datacols.sort()
	    datacols.remove(self.key)
	    cols.extend(datacols)
	if len(self.geokml):
	    cols.extend(["point", "boundary"])
	if self.output is None:
	    out = sys.stdout
	else:
	    out = open(self.output, "a")
	if self.verbose:
	    print cols
	cw = csv.DictWriter(out, cols)
	cw.writeheader()
	if len(self.data) > 0:
	    datakeys = self.data.keys()
	    datakeys.sort()
	    for x in datakeys:
		if len(self.geokml):
		    x_geo = self.getGeoNumber(x)
		    if x_geo is None:
			continue
		    row = { self.key: x, "point": self.geokml[x_geo]["point"], "boundary": self.geokml[x_geo]["boundary"] }
		    row = dict(row.items() + self.data[x].items())
		else:
		    row = self.data[x]
		cw.writerow(row)
	elif self.geokml is not None:
	    geokmlkeys = self.geokml.keys()
	    geokmlkeys.sort()
	    for x in geokmlkeys:
		row = { self.key: x, "point": self.geokml[x]["point"], "boundary": self.geokml[x]["boundary"] }
		cw.writerow(row)
    
    def genKml(self):
	if self.verbose:
	    print "generating KML..."
	self.genKmlGeo()
	if self.output is None:
	    print kmldom.SerializePretty(self.kml)
	else:
	    f = open(self.output, "a")
	    f.write(kmldom.SerializePretty(self.kml))
	    f.close()

    def genKmlGeo(self):
	docu = self.factory.CreateDocument()
	self.kml = self.factory.CreateElementById(kmldom.Type_kml)
	kmlfile = kmlengine.KmlFile.CreateFromImport(self.kml)
	self.kml = kmldom.AsKml(kmlfile.get_root())
	self.kml.set_feature(docu)
	if len(self.data) > 0:
	    keys = self.data.keys()
	elif self.geokml is not None:
	    keys = self.geokml.keys()
    	keys.sort()
	for x in keys:
	    x_geo = self.getGeoNumber(x)
	    x_safe = x_geo.replace("/", "_")
	    geoprefix = self.geotable.replace("_","")
	    plid = geoprefix + "-" + x_safe
	    if x_geo is None:
		continue
	    pl = self.factory.CreatePlacemark()
	    pl.set_name(x)
	    pl.set_id(plid)
	    point_kml = self.geokml[x_geo]["point"]
	    point_text = ''
	    if type(point_kml) is types.ListType:
		try:
		    point_kml = "".join(point_kml)
		except TypeError:
		    point_kml = ""
	    if "boundary" in self.geokml[x_geo]:
		bounds_kml = self.geokml[x_geo]["boundary"]
		if type(bounds_kml) is types.ListType:
		    try:
			bounds_kml = "".join(bounds_kml)
		    except:
			continue
		if bounds_kml.startswith('<Polygon>'):
		    bounds_kml = '<MultiGeometry>' + bounds_kml + '</MultiGeometry>'
		try:
		    bounds_kml = bounds_kml.replace("</MultiGeometry><MultiGeometry>", "")
		    bounds_points_kml = bounds_kml.replace("<MultiGeometry>", "<MultiGeometry>" + point_kml)
		    kmlfile,errors = kmlengine.KmlFile.CreateFromParse(bounds_points_kml)
		except:
		    bounds_kml = self.geokml[x_geo]["boundary"][0]
		    bounds_points_kml = bounds_kml.replace("<MultiGeometry>", "<MultiGeometry>" + point_kml)
		    kmlfile,errors = kmlengine.KmlFile.CreateFromParse(bounds_points_kml)
		mg = kmldom.AsMultiGeometry(kmlfile.get_root())
	    else:
		kmlfile,errors = kmlengine.KmlFile.CreateFromParse("<MultiGeometry>"+point_kml+"</MultiGeometry>")
		mg = kmldom.AsMultiGeometry(kmlfile.get_root())
	    pl.set_geometry(mg)
	    pl.set_styleurl('#' + plid)
	    docu.add_feature(pl)

    def gen(self):
	if self.outputformat == "csv":
	    self.genCsv()
	else:
	    self.genKml()

    def getGeoNumber(self, x):
	x_geo = x.strip()
	if x_geo not in self.geokml:
	    m = re.match(r"([\d/]+)", x_geo)
	    if m is not None:
		x_geo = m.group(0) # x_geo is numeric
		if x_geo + "L" in self.geokml: # large
		    x_geo += "L"
		elif x_geo + "S" in self.geokml: # small
		    x_geo += "S"
		else: # cannot find suffixed geo number
		    return None
	    else:
		return None # x_geo doesn't start with a number
	return x_geo

def main():
    gc = GeoCensus()
    try:
        opts, args = getopt.getopt(sys.argv[1:], "chkvo:g:t:d:", ["help", "output=", "--geo", "--tolerance", "--data", "csv", "kml", "--key"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        gc.usage()
        sys.exit(2)
    if len(sys.argv) <= 1:
        gc.usage()
	sys.exit()
    for o, a in opts:
        if o == "-v":
            gc.verbose = True
        elif o in ("-h", "--help"):
            gc.usage()
            sys.exit()
        elif o in ("-o", "--output"):
            gc.output = a
	elif o in ("-g", "--geo"):
	    gc.setGeo(a)
	elif o in ("-t", "--tolerance"):
	    gc.setGeoTolerance(a)
	elif o in ("-d", "--data"):
	    gc.getCensusData(a)
	elif o in ("-c", "--csv"):
	    gc.outputformat = "csv"
	elif o in ("--kml"):
	    gc.outputformat = "kml"
	elif o in ("-k", "--key"):
	    gc.key = a
        else:
            assert False, "unhandled option"
    if gc.verbose:
	print gc.geotable
	print gc.outputformat
    gc.geodb()
    gc.gen()
    # ...

if __name__ == "__main__":
    main()