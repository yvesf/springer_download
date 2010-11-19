#! /usr/bin/env python

# -*- coding: utf-8 -*-

import os
import sys
import getopt
import urllib
import re
import tempfile
import shutil
#import pyPdf later

# Set some kind of User-Agent so we don't get blocked by SpringerLink
class SpringerURLopener(urllib.FancyURLopener):
    version = "Mozilla 5.0"

def pdfcat(fileList, bookTitlePath):
    writer = pyPdf.PdfFileWriter()
    for inputFile in fileList:
        inputPdf = pyPdf.PdfFileReader(file(inputFile, "rb"))
        print "Merge {0}".format(inputFile)
        for pageNum in range(inputPdf.getNumPages()):
            writer.addPage(inputPdf.getPage(pageNum))
    writer.write(file(bookTitlePath, "wb"))

# validate CLI arguments and start downloading
def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hl:s:c:", ["help", "link=","content=","socksaddr=","socksport="])
    except getopt.GetoptError:
        error()

    link = ""
    hash = ""
    socks_port = 1080
    socks_host = None

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-c", "--content"):
            if link != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            hash = arg
        elif opt in ("-l", "--link"):
            if hash != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            match = re.match("(https?://)?(www\.)?springer(link)?.(com|de)/(content|.*book)/(?P<hash>[a-z0-9\-]+)/?(\?[^/]*)?$", arg)
            if not match:
                usage()
                error("Bad link given. See example link.")
            hash = match.group("hash")
        elif opt in ("-s","--socksaddr"):
            socks_host = arg
            log("use socks proxy at {0}\n".format(arg))
        elif opt in ("--socksport"):
            socks_port = int(arg)
            log("set socks port to {0}\n".format(socks_port))

    if hash == "":
      usage()
      error("Either a link or a hash must be given.")

    if socks_host:
            socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, addr=socks_host, port=socks_port, rdns=True)

    baseLink = "http://springerlink.com/content/" + hash + "/"
    link = baseLink + "contents/"
    chapters = list()
    loader = SpringerURLopener();
    curDir = os.getcwd()

    bookTitle = ""
    coverLink = ""

    front_matter = False

    while True:
        # download page source
        try:
            print "fetching book information...\n\t%s" % link
            page = loader.open(link).read()
        except IOError, e:
            error("Bad link given (%s)" % e)

        if re.search(r'403 Forbidden', page):
            error("Could not access page: 403 Forbidden error.")

        if bookTitle == "":
            match = re.search(r'<h1[^<]+class="title">([^<]+)(?:<br/>\s*<span class="subtitle">([^<]+)</span>\s*)?</h1>', page)
            if not match or match.group(1).strip() == "":
                error("Could not evaluate book title - bad link %s" % link)
            else:
                bookTitle = match.group(1).strip()
            # subtitle
            if match and match.group(2) and match.group(2).strip() != "":
                bookTitle += " - " + match.group(2).strip()

            # edition
            #match = re.search(r'<td class="labelName">Edition</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " " + match.group(1).strip()

            ## year
            #match = re.search(r'<td class="labelName">Copyright</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " " + match.group(1).strip()

            ## publisher
            #match = re.search(r'<td class="labelName">Publisher</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " - " + match.group(1).strip()

            # coverimage
            match = re.search(r'<div class="coverImage" title="Cover Image" style="background-image: url\(/content/([^/]+)/cover-medium\.gif\)">', page)
            if match:
                coverLink = "http://springerlink.com/content/" + match.group(1) + "/cover-large.gif"

            bookTitlePath = curDir + "/%s.pdf" % sanitizeFilename(bookTitle)
            if bookTitlePath == "":
                error("could not transliterate book title %s" % bookTitle)
            if os.path.isfile(bookTitlePath):
                error("%s already downloaded" % bookTitlePath)

            print "\nNow Trying to download book '%s'\n" % bookTitle
            #error("foo")

        # get chapters
        for match in re.finditer('href="([^"]+\.pdf)"', page):
            chapterLink = match.group(1)
            if chapterLink[:7] == "http://": # skip external links
                continue

            if re.search(r'front-matter.pdf', chapterLink):
                if front_matter:
                    continue
                else:
                    front_matter = True
            if re.search(r'back-matter.pdf', chapterLink) and re.search(r'<a href="([^"]+)">Next</a>', page):
                continue
            #skip backmatter if it is in list as second chapter - will be there at the end of the book also
            if re.search(r'back-matter.pdf', chapterLink):
                if len(chapters)<2:
                    continue

            chapters.append(chapterLink)

        # get next page
        match = re.search(r'<a href="([^"]+)">Next</a>', page)
        if match:
            link = "http://springerlink.com" + match.group(1).replace("&amp;", "&")
        else:
            break

    if len(chapters) == 0:
        error("No chapters found - bad link?")

    print "found %d chapters" % len(chapters)

    # setup; set tempDir as working directory
    tempDir = tempfile.mkdtemp()
    os.chdir(tempDir)

    i = 1
    fileList = list()

    for chapterLink in chapters:
        if chapterLink[0] == "/":
            chapterLink = "http://springerlink.com" + chapterLink
        else:
            chapterLink = baseLink + chapterLink
        chapterLink = re.sub("/[^/]+/\.\.", "", chapterLink)
        print "downloading chapter %d/%d" % (i, len(chapters))
        localFile, mimeType = geturl(chapterLink, "%d.pdf" % i)

        if mimeType.gettype() != "application/pdf":
            os.chdir(curDir)
            shutil.rmtree(tempDir)
            error("downloaded chapter %s has invalid mime type %s - are you allowed to download %s?" % (chapterLink, mimeType.gettype(), bookTitle))

        fileList.append(localFile)
        i += 1

    if coverLink != "":
        print "downloading front cover from %s" % coverLink
        localFile, mimeType = geturl(coverLink, "frontcover")
        if os.system("convert %s %s.pdf" % (localFile, localFile)) == 0:
            fileList.insert(0, localFile + ".pdf")


    print "merging chapters"
    if len(fileList) == 1:
      shutil.move(fileList[0], bookTitlePath)
    else:
      pdfcat(fileList, bookTitlePath)

    # cleanup
    os.chdir(curDir)
    shutil.rmtree(tempDir)

    print "book %s was successfully downloaded, it was saved to %s" % (bookTitle, bookTitlePath)
    log("downloaded %s chapters (%.2fMiB) of %s\n" % (len(chapters),  os.path.getsize(bookTitlePath)/2.0**20, bookTitle))
    sys.exit()

# give a usage message
def usage():
    print """Usage:
%s [OPTIONS]

Options:
  -h, --help                  Display this usage message
  -l LINK, --link=LINK        defines the link of the book you intend to download
  -c ISBN, --content=ISBN     builds the link from a given ISBN (see below)
  -s SADDR, --socksaddr=SADDR Use given SOCKS Proxy Host.
            --socksport=SPORT  Use given Port to connect SOCKS Proxy (Default: 1080)

You have to set exactly one of these options.

LINK:
  The link to your the detail page of the ebook of your choice on SpringerLink.
  It lists book metadata and has a possibly paginated list of the chapters of the book.
  It has the form:
    http://springerlink.com/content/ISBN/STUFF
  Where: ISBN is a string consisting of lower-case, latin chars and numbers.
         It alone identifies the book you intent do download.
         STUFF is optional and looks like #section=... or similar. It will be stripped.

SADDR,SPORT:
  SOCKS Proxy Address. 
  Remote DNS is enabled. No Authentification supported.
  For use with ssh -D <socksport> <host>

Using a http-proxy:
  you could specify a HTTP-Proxy using the http_proxy environment variable, example:
     $ export http_proxy="http://localhost:3128"
     $ ./springer_download.py -l "http://...."
""" % os.path.basename(sys.argv[0])

# raise an error and quit
def error(msg=""):
    if msg != "":
        log("ERR: " + msg + "\n")
        print "\nERROR: %s\n" % msg
    sys.exit(2)

    return None

# log to file
def log(msg=""):
    logFile = open('springer_download.log', 'a')
    logFile.write(msg)
    logFile.close()

# based on http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def findInPath(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, prog)
        if os.path.exists(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file
    return False

# based on http://mail.python.org/pipermail/python-list/2005-April/319818.html
def _reporthook(numblocks, blocksize, filesize, url=None):
    #XXX Should handle possible filesize=-1.
    try:
        percent = min((numblocks*blocksize*100)/filesize, 100)
    except:
        percent = 100
    if numblocks != 0:
        sys.stdout.write("\b"*70)
    sys.stdout.write("%-66s%3d%%" % (url, percent))

def geturl(url, dst):
    downloader = SpringerURLopener()
    if sys.stdout.isatty():
        response = downloader.retrieve(url, dst,
                           lambda nb, bs, fs, url=url: _reporthook(nb,bs,fs,url))
        sys.stdout.write("\n")
    else:
        response = downloader.retrieve(url, dst)

    return response

def sanitizeFilename(filename):
    return re.sub("\s+", "_", unicode(filename, "utf8").encode("ascii", "replace").replace("/","-"))

sys.path.append(os.path.join(os.path.dirname(sys.argv[0]), "lib/pyPdf"))
try:
    import pyPdf
except ImportError:
    error("Failed to import pyPdf. May not be installed or you need to run git submodule init; git submodule update")

sys.path.append(os.path.join(os.path.dirname(sys.argv[0]), "lib/socksipy"))
try:
    import socket
    import socks
    socket.socket = socks.socksocket
except ImportError:
    log("Error importing socks")
    class socks:
        PROXY_TYPE_SOCKS5=None
        @staticmethod
        def setdefaultproxy(*a,**kw):
            error("Socks not available. install python-socksipy")

# start program
if __name__ == "__main__":
    main(sys.argv[1:])

# kate: indent-width 4; replace-tabs on;
