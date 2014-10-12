#!/usr/bin/env python

"""ppimg

Usage:
  ppimg [-bcdiqvw] <infile> [<outfile>]
  ppimg [-dqv] --gettargetwidth=<image>
  ppimg [-dqv] --calcimagewidths --maxwidth=<maxwidth> <infile>
  ppimg -h | --help
  ppimg ---version

Performs various tasks related to illustrations in the post-processing of 
books for pgdp.org using the ppgen post-processing tool.

Examples:
  ppimg book-src.txt
  ppimg book-src.txt book-src2.txt

Options:
  -b, --boilerplate    Generate HTML boilerplate code from .il/.ca markup. 
  -c, --check          Check for issues with .il markup
  -d, --dryrun         Run through conversions but do not write out result
  -i, --illustrations  Convert raw [Illustration] tags into ppgen .il/.ca markup.
  -q, --quiet          Print less text.
  -v, --verbose        Print more text.
  -w, --updatewidths   Update .il width parameters to files pixel dimensions.
  -h, --help           Show help.
  --version            Show version.
"""  

from docopt import docopt
from PIL import Image
from bs4 import BeautifulSoup
import glob
import re
import os
import sys
import logging
import subprocess
import json
import shlex

def isLineBlank( line ):
	return re.match(r"^\s*$", line)
	
	
def isLineComment( line ):
	return re.match(r"^\/\/ *$", line)
	
	
def idFromFilename( fn ):
	id = os.path.basename(fn) # strip to filename only
	id = os.path.splitext(id)[0] # strip off extension
	return id
	
	
def idFromPageNumber( pn ):
	id =  'i_{}'.format(pn)
	return id
	
	
def findPreviousNonEmptyLine( buf, startLine ):
	lineNum = startLine
	while lineNum < len(buf) and isLineBlank(buf[lineNum]):
		lineNum -= 1
	
	return lineNum
	
	
def findNextNonEmptyLine( buf, startLine ):
	lineNum = startLine
	while lineNum >= 0 and isLineBlank(buf[lineNum]):
		lineNum += 1
	
	return lineNum
	
	
# For a given ppgen command, parse all arguments in the form
# 	arg="val"
# 	arg='val'
# 	arg=val
#
def parseArgs(commandLine):
	arguments = {}
	
	# break up command line 
	tokens = shlex.split(commandLine)
#	print(tokens)
	
	# process parameters (skip .command)
	for t in tokens[1:]:
		t = re.sub(r"[\'\"]","",t)
		m = re.match(r"(.+)=(.+)", t)
		if m:
			arguments[m.group(1)]=m.group(2)
		
	return(arguments)


def buildImageDictionary():
	# Build dictionary of image files in images/ directory
	files = sorted(glob.glob("images/*"))
	
	logging.info("------ Taking inventory of /image folder")
	images = {}
	for f in files:
		try:
			img = Image.open(f)
			img.load()
		except IOError:
			logging.warning("Error loading '{}' ... skipping".format(f))
		except:
			raise
		else:
			fn = os.path.basename(f)
			anchorID = idFromFilename(fn)
			logging.debug("Found image id={} fn='{}' size={}".format(anchorID,fn,img.size))
			scanPageNum = re.sub("[^0-9]","",fn)
			key = idFromFilename(fn)
			images[key] = ({'anchorID':anchorID, 'fileName':fn, 'scanPageNum':scanPageNum, 'dimensions':img.size, 'caption':"", 'usageCount':0 })

			if not re.match(r"i_\d{3,4}[a-z]?\.", fn):
				logging.warning("File '{}' does not match expected naming convention (i_001, i_001a)".format(fn))
		
#	print(images)
	logging.info("--------- Found {} images".format(len(images)))
	
	return images;
	
	
def parseIllustrationBlocks( inBuf ):
	outBuf = []
	lineNum = 0
	currentScanPage = 0;
	illustrations = {};
	
	logging.info("------ Parsing .il/.ca statements from input")
	while lineNum < len(inBuf):
		# Keep track of active scanpage, page numbers must be 
		m = re.match(r"\/\/ (\d+)\.[png|jpg|jpeg]", inBuf[lineNum])
		if m:
			currentScanPage = m.group(1)
#			logging.debug("------ Processing page "+currentScanPage)

		# Find next .il/.ca, discard all other lines
		if re.match(r"^\.il ", inBuf[lineNum]):
			logging.debug("Line {}: Found .il '{}'".format(lineNum,inBuf[lineNum]))
			startLine = lineNum
			inBlock = []
			captionBlock = []

			ilStatement = inBuf[lineNum]
			inBlock.append(inBuf[lineNum])			
			lineNum += 1

			ilParams = parseArgs(ilStatement)

			# Is there a caption?
			if re.match(r"^\.ca", inBuf[lineNum]):
				# Is .ca single line style?
				if re.match(r"^\.ca \S+", inBuf[lineNum]):
					inBlock.append(inBuf[lineNum])
					caption = re.sub("^\.ca ","", inBuf[lineNum]) # strip ".ca "
					captionBlock.append(caption)
					lineNum += 1
				# Its a block
				else:
					# Copy caption block
					inBlock.append(inBuf[lineNum])
					while not re.match(r"^\.ca\-", inBuf[lineNum]):
						lineNum += 1
						inBlock.append(inBuf[lineNum])
						captionBlock.append(inBuf[lineNum])
				
				endLine = lineNum + 1
			
			else:
				endLine = lineNum
			
			# Add entry in dictionary (empty for now)
			key = idFromFilename(ilParams['fn'])
			illustrations[key] = ({'ilStatement':ilStatement, 'captionBlock':captionBlock, 'ilBlock':inBlock, 'HTML':"", 'startLine':startLine, 'endLine':endLine, 'ilParams':ilParams, 'scanPageNum':currentScanPage })
		else:
			# Ignore lines that aren't .il/.ca
			lineNum += 1
		
	logging.info("--------- Found {} .il statements".format(len(illustrations)))

	return illustrations
	

def buildBoilerplateDictionary( inBuf ):
	outBuf = []
	lineNum = 0
	
	boilerplate = {};
	illustrations = parseIllustrationBlocks(inBuf)
	
	logging.info("------ Generating temporary ppgen source file containing parsed .il/.ca statements")
	tempFileName = "ppimgtempsrc" # TODO: use tempfile functions instead? will clobber existing if named exists
	f = open(tempFileName,'w')
	for k, il in illustrations.items():
		for line in il['ilBlock']:
			f.write(line+'\n')
		f.write('\n')
	f.close()
	
	logging.info("------ Running ppgen against temporary ppgen source file")
	ppgenCommandLine=['ppgen','-i',tempFileName] # TODO: this wont work on windows..
	proc=subprocess.Popen(ppgenCommandLine)
	proc.wait()
	if proc.returncode != 0:
		logging.critical("Error occured during ppgen processing")

	logging.info("------ Parsing ppgen generated HTML")
	# Open ppgen generated HTML and represent as an array of lines
	infile = tempFileName + ".html"
	inBuf = loadFile(infile)
	
	logging.info("--------- Parsing CSS")
	cssLines = []
	
	for line in inBuf:
		# .ic001 {
		# .id001 {
		# @media handheld { .ic001 {
		# .ig001 {
		# .fig(left|right|center)
		if( re.search(r"\.i[cdg]\d+ {", line) or \
			re.search(r"\.fig(left|right|center)", line) ):
			line = re.sub("(\s{2,}|\t)","",line) # get rid of whitespace in front
			cssLines.append(line)
			logging.debug("Add css: "+line)
			
	logging.info("--------- Parsing HTML")
	# Soupify HTML
	soup = BeautifulSoup(open(infile))
	ilBlocks = soup.find_all('div',id=re.compile("$"))
	for il in ilBlocks:
		src = il.img['src']
		key = idFromFilename(src)
		illustrations[key]['HTML'] = str(il);
		
	return illustrations, cssLines


def generateHTMLBoilerplate( inBuf ):
#psuedocode:
# create temporary ppgen source file that contains only .il/.ca lines 
# run ppgen on temporary source file 
# parse CSS (related to illustrations/captions) and illustration related HTML from output
# using parsed css, add .de statements to output
# replace existing .il/.ca statements with 
#	 .if t
#	 original .il/.ca statements
#	 .if-
#	 .if h
#    .li
#	 parsed HTML
#    .li-
#	 .if-

	logging.info("--- Generating HTML Boilerplate")
	
	boilerplate, cssLines = buildBoilerplateDictionary(inBuf)
	
	logging.info("--- Adding boilerplate to original")
	outBuf = []
	logging.info("------ Adding CSS")	
	for line in cssLines:
		outBuf.append(".de " + line)
	
	logging.info("------ Adding HTML")	
	lineNum = 0
	while lineNum < len(inBuf):
		if re.match(r"^\.il ", inBuf[lineNum]):
			
			ilParams = parseArgs(inBuf[lineNum])
			ilKey = idFromFilename(ilParams['fn'])

			# Sanity check.. TODO: is it legal for multiple illustrations to share the same id?
			if boilerplate[ilKey]['startLine'] != lineNum:
				logging.warning("Illustration id='{}' found on unexpected line {}".format(ilKey,lineNum))
			
			# Replace .il/.ca block with HTML
			outBuf.append(".if t")
			# original .il/.ca statements
			for line in boilerplate[ilKey]['ilBlock']:
				outBuf.append(line)
			outBuf.append(".if-")
			outBuf.append(".if h")
			outBuf.append(".li")
			outBuf.append(boilerplate[ilKey]['HTML'])
			outBuf.append(".li-")
			outBuf.append(".if-")

			lineNum = boilerplate[ilKey]['endLine']
			
		else:
			outBuf.append(inBuf[lineNum])
			lineNum += 1

	return outBuf
	
def convertRawIllustrationMarkup( inBuf ):
	# Replace [Illustration: caption] markup with equivalent .il/.ca statements
	outBuf = []
	lineNum = 0
	currentScanPage = 0
	illustrationTagCount = 0
	asteriskIllustrationTagCount = 0
		
	logging.info("--- Processing illustrations")
	
	illustrations = buildImageDictionary()
	
	logging.info("------ Converting [Illustration] tags")
	while lineNum < len(inBuf):
		# Keep track of active scanpage, page numbers must be 
		m = re.match(r"\/\/ (\d+)\.[png|jpg|jpeg]", inBuf[lineNum])
		if m:
			currentScanPage = m.group(1)
#			logging.debug("------ Processing page "+currentScanPage)

		# Copy until next illustration block
		if re.match(r"^\[Illustration", inBuf[lineNum]) or re.match(r"^\*\[Illustration", inBuf[lineNum]):
			inBlock = []
			outBlock = []
		
			# *[Illustration:] tags need to be handled manually afterward (can't reposition before or illustration will change page location)
			if re.match(r"^\*\[Illustration", inBuf[lineNum]):
				asteriskIllustrationTagCount += 1
			else:
				illustrationTagCount += 1

			# Copy illustration block
			inBlock.append(inBuf[lineNum])
			while lineNum < len(inBuf)-1 and not re.search(r"]$", inBuf[lineNum]):
				lineNum += 1
				inBlock.append(inBuf[lineNum])
			
			lineNum += 1
			
			# Handle multiple illustrations per page, must be named (i_001a, i_001b, ...) or (i_001, i_001a, i_001b, ...)
			ilID = None
			testID = idFromPageNumber(currentScanPage)
			if testID in illustrations and illustrations[testID]['usageCount'] == 0:
				ilID = testID
			else: # try i_001a, i_001b, ..., i_001z
				alphabet = map(chr, range(97,123))
				for letter in alphabet:
					if testID+letter in illustrations and illustrations[testID+letter]['usageCount'] == 0:
						ilID = testID+letter
						break;
			
			if ilID == None and testID in illustrations:
				ilID = testID
			elif ilID == None:
				logging.critical("No image file for illustration located on scan page {}.png".format(currentScanPage));
					
			# Convert to ppgen illustration block
			# .il id=i001 fn=i_001.jpg w=600 alt=''
			outBlock.append(".il id=" + ilID + " fn=" +  illustrations[ilID]['fileName'] + " w=" + str(illustrations[ilID]['dimensions'][0]) + "px" + " alt=''")
			illustrations[ilID]['usageCount'] += 1
			
			# Extract caption from illustration block
			captionBlock = []
			for line in inBlock:
				line = re.sub(r"^\[Illustration: ", "", line)
				line = re.sub(r"^\[Illustration", "", line)
				line = re.sub(r"]$", "", line)
				captionBlock.append(line)

		    # .ca SOUTHAMPTON BAR IN THE OLDEN TIME.
			if len(captionBlock) == 1 and captionBlock[0] == "":
				# No caption
				pass
			elif len(captionBlock) == 1:
				# One line caption
				outBlock.append(".ca " + captionBlock[0]);
			else:
				# Multiline caption
				outBlock.append(".ca");
				for line in captionBlock:
					outBlock.append(line)
				outBlock.append(".ca-");
							
			# Write out ppgen illustration block
			for line in outBlock:
				outBuf.append(line)
			
			logging.debug("Line " + str(lineNum) + ": ScanPage " + str(currentScanPage) + ": convert " + str(inBlock))

		else:
			outBuf.append(inBuf[lineNum])
			lineNum += 1
	
	logging.info("------ Processed {} [Illustrations] tags".format(illustrationTagCount))
	if asteriskIllustrationTagCount > 0:
		logging.warning("Found {} *[Illustrations] tags; ppgen .il/.ca statements have been generated, but relocation to paragraph break must be performed manually.".format(asteriskIllustrationTagCount))

	return outBuf;
		
		
def generateIlStatement( args ):
	ilStatement = ".il"

	# Add quotes where needed (parameters with spaces)
	for k, v in args.items():
		if ' ' in v:
			args[k] = "'{}'".format(args[k])

	# Add parameters individually so that order is deterministic
	if 'id' in args:
		ilStatement += " id={}".format(args['id'])
		del args['id']
	if 'fn' in args:
		ilStatement += " fn={}".format(args['fn'])
		del args['fn']
	if 'link' in args:
		ilStatement += " link={}".format(args['link'])
		del args['link']
	if 'alt' in args:
		ilStatement += " alt={}".format(args['alt'])
		del args['alt']
	if 'w' in args:
		ilStatement += " w={}".format(args['w'])
		del args['w']
	if 'ew' in args:
		ilStatement += " ew={}".format(args['ew'])
		del args['ew']
	if 'eh' in args:
		ilStatement += " eh={}".format(args['eh'])
		del args['eh']
	if 'align' in args:
		ilStatement += " align={}".format(args['align'])
		del args['align']

	# Add any remaining parameters whose order we dont care about, or didn't 
	# exist at the time
	for k, v in args.items():
		kv = " {}={}".format(k,v)
		ilStatement += kv

	return ilStatement
	
			
def updateWidths( inBuf ):
	outBuf = inBuf
	
	logging.info("--- Updating widths")

	illustrations = parseIllustrationBlocks(inBuf)
	images = buildImageDictionary()
	
	# update width parameter in each .il statement
	logging.info("------ Modifying .il statements to match actual width dimension of image file")
	for k, il in illustrations.items():
		logging.debug("Original .il: {}".format(il['ilStatement']))

		ilParams = il['ilParams']
		curWidth = ilParams['w']
		
		if "%" in curWidth:
			ilParams['ew'] = curWidth
		
		key = idFromFilename(ilParams['fn'])
		imageFileWidth = images[key]['dimensions'][0]
		ilParams['w'] = "{}px".format(imageFileWidth)
		
		#TODO: bug here.. if multiple .il statements exist for the same file only the last instance will be modified
		newIlStatement = generateIlStatement(ilParams)	
		outBuf[il['startLine']] = newIlStatement

		logging.debug("Modified .il: {}".format(newIlStatement))
	
	return outBuf
	
			
def loadFile(fn):
	inBuf = []
	encoding = ""
	
	if not os.path.isfile(fn):
		logging.critical("specified file '{}' not found".format(fn))

	if encoding == "":
		try:
			wbuf = open(fn, "r", encoding='ascii').read()
			encoding = "ASCII" # we consider ASCII as a subset of Latin-1 for DP purposes
			inBuf = wbuf.split("\n")
		except Exception as e:
			pass

	if encoding == "":
		try:
			wbuf = open(fn, "rU", encoding='UTF-8').read()
			encoding = "utf_8"
			inBuf = wbuf.split("\n")
			# remove BOM on first line if present
			t = ":".join("{0:x}".format(ord(c)) for c in inBuf[0])
			if t[0:4] == 'feff':
				inBuf[0] = inBuf[0][1:]
		except:
			pass

	if encoding == "":
		try:
			wbuf = open(fn, "r", encoding='latin_1').read()
			encoding = "latin_1"
			inBuf = wbuf.split("\n")
		except Exception as e:
			pass

	if encoding == "":
		fatal("Cannot determine input file decoding")
	else:
		if encoding == "ASCII":
			encoding = "latin_1" # handle ASCII as Latin-1 for DP purposes

	for i in range(len(inBuf)):
		inBuf[i] = inBuf[i].rstrip()

	return inBuf;
	
	
def createOutputFileName( infile ):
	# TODO make this smart.. is infile raw or ppgen source? maybe two functions needed
	outfile = infile.split('.')[0] + "-out.txt"
	return outfile


def getTargetWidth( image ):
	json_data=open('images.json')

	data = json.load(json_data)
	width = data[image]['targetWidth']
	json_data.close()
	
	return width

def loadJSON( fn ):
	data = {}
	try:
		with open(fn) as f:
			data = json.load(f)
	except FileNotFoundError:
		logging.info("------ JSON file '{}' not found, using empty dictionary".format(fn))
		pass
	except:
		raise
	else:
		logging.info("------ Loaded JSON from file '{}'".format(fn))
		
		
	return data
		

def calcImageWidths( inBuf, maxwidth ):
	logging.info("--- Calculating widths")

	illustrations = parseIllustrationBlocks(inBuf)
#	images = buildImageDictionary()
	
	jsonData = loadJSON("images.json")
	
	for k, il in illustrations.items():
		ilParams = il['ilParams']
		
		# Check image percentage
		if "%" in ilParams['w']:
			scale = int(re.sub("%", "", ilParams['w'])) / 100.0
		elif "%" in ilParams['ew']:
			scale = int(re.sub("%", "", ilParams['ew'])) / 100.0
		else:
			scale = 0
			logging.error("w or ew parameter must be expressed in % for width to be calculated")
		
		calculatedWidth = int(scale * int(maxwidth))
	
		# Add to data
		key = "images/"+ilParams['fn']
		logging.debug("Key: {}, Calculated width: {}".format(key, calculatedWidth))
		jsonData[key] = ({'targetWidth':calculatedWidth})
#		images[scanPageNum] = ({'anchorID':anchorID, 'fileName':f, 'scanPageNum':scanPageNum, 'dimensions':img.size, 'caption':"", 'usageCount':0 })
		
	logging.info("------ Updating images.json with calculated widths")
	# Write out JSON
	f = open("images.json",'w')
	f.write(json.dumps(jsonData))
	f.close()
	
	# Change last modifed time of illustration masters to force resize on next invocation of make
	masterImageFiles = glob.glob(os.path.abspath('originals/illustrations')+'/*')
	commandLine=['touch'] + masterImageFiles # TODO: this wont work on windows..
	proc=subprocess.Popen(commandLine)
	proc.wait()
	if proc.returncode != 0:
		logging.critical("Error occured processing {}".format(commandLine))
	
	logging.info("*************************************************")
	logging.info("***                                          ****")
	logging.info("***  RUN 'make' TO RESCALE FILES IN images/  ****")
	logging.info("***  THEN 'ppimg -w' TO UPDATE PPGEN SRC     ****")
	logging.info("***                                          ****")
	logging.info("*************************************************")


def main():
	args = docopt(__doc__, version='ppimg 0.1')

	# Configure logging
	logLevel = logging.INFO #default
	if args['--verbose']:
		logLevel = logging.DEBUG
	elif args['--quiet']:
		logLevel = logging.ERROR
		
	logging.basicConfig(format='%(levelname)s: %(message)s', level=logLevel)			
	logging.debug(args)
			
	if args['--gettargetwidth']:
		width = getTargetWidth(args['--gettargetwidth'])
		print(width)

	else:
		# Process required command line arguments
		outfile = createOutputFileName(args['<infile>'])
		if args['<outfile>']:
			outfile = args['<outfile>']
			
		infile = args['<infile>']

		# Open source file and represent as an array of lines
		inBuf = loadFile(infile)

		# Process optional command line arguments
		doBoilerplate = args['--boilerplate']
		doIllustrations = args['--illustrations']
		doUpdateWidths = args['--updatewidths']
		calcimagewidths = args['--calcimagewidths']
		
		# Default TODO (smart based on what is given? raw/ppgen source)
	#	if( not doBoilerplate and \
	#		not doIllustrations ):
	#		doIllustrations = True;
			
		# Process source document
		logging.info("Processing '{}' to '{}'".format(infile,outfile))
		outBuf = []
		if doIllustrations:
			outBuf = convertRawIllustrationMarkup(inBuf)
			inBuf = outBuf
		elif doBoilerplate:
			outBuf = generateHTMLBoilerplate(inBuf)
			inBuf = outBuf
		elif doUpdateWidths:
			outBuf = updateWidths(inBuf)
			inBuf = outBuf
		elif calcimagewidths:
			calcImageWidths(inBuf, args['--maxwidth'])

		if outBuf and not args['--dryrun']:
			# Save file
			f = open(outfile,'w')
			for line in outBuf:
				f.write(line+'\n')
			f.close()
	
	return


if __name__ == "__main__":
	main()
