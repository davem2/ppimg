#!/usr/bin/env python

"""ppimg

Usage:
  ppimg [-biqv] <infile>
  ppimg [-biqv] <infile> <outfile>
  ppimg -h | --help
  ppimg ---version

Performs various tasks related to illustrations in the post-processing of 
books for pgdp.org using the ppgen post-processing tool.

Examples:
  ppimg book.txt
  ppimg book-src.txt book-src.txt

Options:
  -h --help            Show help.
  -b, --boilerplate    Include HTML boilerplate code when processing illustrations 
  -i, --illustrations  Convert [Illustration] tags into ppgen .il/.ca markup.
  -q, --quiet          Print less text.
  -v, --verbose        Print more text.
  --version            Show version.
"""  

from docopt import docopt
from PIL import Image
import glob
import re
import os
import sys
import logging


def isLineBlank( line ):
	return re.match( r"^\s*$", line )
	
	
def isLineComment( line ):
	return re.match( r"^\/\/ *$", line )
	
	
def formatAsID( s ):
	s = re.sub(r" ", '_', s)        # Replace spaces with underscore    
	s = re.sub(r"[^\w\s]", '', s)   # Strip everything but alphanumeric and _
	s = s.lower()                   # Lowercase

	return s
	
	
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
	
	
def processIllustrations( inBuf, doBoilerplate ):
	# Build dictionary of images
	files = sorted(glob.glob("images/*"))
	
	logging.info("--- Processing illustrations")
	logging.info("------ Scanning /image folder")

	# Build dictionary of illustrations in images folder
	illustrations = {}
	for f in files:
		try:
			img = Image.open(f)
			img.load()
		except:
			logging.critical("Unable to load image: " + f)

		m = re.match(r"images/i_([^\.]+)", f)
		if( m ):        
			scanPageNum = m.group(1)
			anchorID = "i"+scanPageNum
			f = re.sub(r"images/", "", f)
			illustrations[scanPageNum] = ({'anchorID':anchorID, 'fileName':f, 'scanPageNum':scanPageNum, 'dimensions':img.size, 'caption':"", 'usageCount':0 })
			logging.debug("Adding image '" + f + "' " + str(img.size))
		else:
			logging.warning("Skipping file '" + f + "' does not match expected naming convention")

	logging.info("------ Found " + str(len(illustrations)) + " illustrations")
	
	# Find and replace [Illustration: caption] markup
	outBuf = []
	lineNum = 0
	currentScanPage = 0
	illustrationTagCount = 0
	asteriskIllustrationTagCount = 0
		
	logging.info("------ Processing [Illustration] tags")

	while lineNum < len(inBuf):
		# Keep track of active scanpage
		m = re.match(r"\/\/ (\d+)\.[png|jpg|jpeg]", inBuf[lineNum])
		if( m ):
			currentScanPage = m.group(1)

		# Copy until next illustration block
		if( re.match(r"^\[Illustration", inBuf[lineNum]) or re.match(r"^\*\[Illustration", inBuf[lineNum]) ):
			inBlock = []
			outBlock = []
		
			# *[Illustration:] tags need to be handled manually afterward (can't reposition before or illustration will change page location)
			if( re.match(r"^\*\[Illustration", inBuf[lineNum]) ):
				asteriskIllustrationTagCount += 1
			else:
				illustrationTagCount += 1

			# Copy illustration block
			inBlock.append(inBuf[lineNum])
			while( lineNum < len(inBuf)-1 and not re.search(r"]$", inBuf[lineNum]) ):
				lineNum += 1
				inBlock.append(inBuf[lineNum])
			
			lineNum += 1
			
			# Handle multiple illustrations per page, must be named (i_001a, i_001b, ...) or (i_001, i_001a, i_001b, ...)
			illustrationKey = None
			if( currentScanPage in illustrations and illustrations[currentScanPage]['usageCount'] == 0 ):
				illustrationKey = currentScanPage
			elif( currentScanPage+'a' in illustrations and illustrations[currentScanPage+'a']['usageCount'] == 0 ):
				illustrationKey = currentScanPage+'a'
			elif( currentScanPage+'b' in illustrations and illustrations[currentScanPage+'b']['usageCount'] == 0 ):
				illustrationKey = currentScanPage+'b'
			elif( currentScanPage+'c' in illustrations and illustrations[currentScanPage+'c']['usageCount'] == 0 ):
				illustrationKey = currentScanPage+'c'
			elif( currentScanPage+'d' in illustrations and illustrations[currentScanPage+'d']['usageCount'] == 0 ):
				illustrationKey = currentScanPage+'d'
			elif( currentScanPage in illustrations ):
				illustrationKey = currentScanPage
			else:
				logging.critical("No image file for illustration located on scan page " + currentScanPage + ".png");
				
			
			# Convert to ppgen illustration block
			# .il id=i_001 fn=i_001.jpg w=600 alt=''
			outBlock.append( ".il id=i" + illustrationKey + " fn=" +  illustrations[illustrationKey]['fileName'] + " w=" + str(illustrations[illustrationKey]['dimensions'][0]) + " alt=''" )
			illustrations[illustrationKey]['usageCount'] += 1
			
			# Extract caption from illustration block
			captionBlock = []
			for line in inBlock:
				line = re.sub(r"^\[Illustration: ", "", line)
				line = re.sub(r"^\[Illustration", "", line)
				line = re.sub(r"]$", "", line)
				captionBlock.append(line)

		   # .ca SOUTHAMPTON BAR IN THE OLDEN TIME.
			if( len(captionBlock) == 1 ):
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
			
			if( doBoilerplate ):
				# Write out boilerplate code for HTML version as comment in case .il is not sufficient
				outBuf.append(".ig  // *** PPPREP BEGIN **************************************************************")
				outBuf.append("// ******** Alternative inline HTML version for use when .il .ca are insufficient *****") 
				outBuf.append(".if h")
				outBuf.append(".de .customCSS { clear:left; float:left; margin:4% 4% 4% 0; }")
				outBuf.append(".li")
				outBuf.append("<div class='customCSS'>")
				outBuf.append("<img src='" + illustrations[currentScanPage]['fileName'] + "' alt='' />")
				outBuf.append("</div>")
				outBuf.append(".li-")
				outBuf.append(".if-")
				outBuf.append(".if t")
				for line in inBlock:
					outBuf.append(line)
				outBuf.append(".if-")           
				outBuf.append(".ig- // *** END ***********************************************************************")
			
			logging.debug("Line " + str(lineNum) + ": ScanPage " + str(currentScanPage) + ": convert " + str(inBlock))

		else:
			outBuf.append(inBuf[lineNum])
			lineNum += 1
	
	logging.info("------ Processed " + str(illustrationTagCount) + " [Illustrations] tags")
	logging.warning("Found " + str(asteriskIllustrationTagCount) + " *[Illustrations] tags; ppgen .il/.ca statements have been generated, but relocation to paragraph break must be performed manually.")

	return outBuf;
		
			
def loadFile(fn):
	inBuf = []
	encoding = ""
	
	if not os.path.isfile(fn):
		logging.critical("specified file {} not found" + format(fn))

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
		# self.info("input file is: {}".format(encoding))
		if encoding == "ASCII":
			encoding = "latin_1" # handle ASCII as Latin-1 for DP purposes

	for i in range(len(inBuf)):
		inBuf[i] = inBuf[i].rstrip()

	return inBuf;
	
	
def createOutputFileName( infile ):
	outfile = infile.split('.')[0] + "-src.txt"
	return outfile


def main():
	args = docopt(__doc__, version='ppimg 0.1')

	# Process required command line arguments
	outfile = createOutputFileName( args['<infile>'] )
	if( args['<outfile>'] ):
		outfile = args['<outfile>']
		
	infile = args['<infile>']

	# Open source file and represent as an array of lines
	inBuf = loadFile( infile )

	# Process optional command line arguments
	doBoilerplate = args['--boilerplate'];
	doIllustrations = args['--illustrations'];
	
	# Default to TODO
	if( not doBoilerplate and \
		not doIllustrations ):
		doIllustrations = True;
		doBoilerplate = True;
			
	# Configure logging
	logLevel = logging.INFO #default
	if( args['--verbose'] ):
		logLevel = logging.DEBUG
	elif( args['--quiet'] ):
		logLevel = logging.ERROR
		
	logging.basicConfig(format='%(levelname)s: %(message)s', level=logLevel)
			
	logging.debug(args)
			
	# Process source document
	logging.info("Processing '" + infile + "' to '" + outfile + "'")
	outBuf = []
	if( doIllustrations ):
		outBuf = processIllustrations( inBuf, doBoilerplate ) # Illustration process requires // 001.png format
		inBuf = outBuf

	# Save file
	f = open(outfile,'w')
	for line in outBuf:
		f.write(line+'\n')
	f.close()
	
	return


if __name__ == "__main__":
	main()
