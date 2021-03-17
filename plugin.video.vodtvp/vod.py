# -*- coding: utf-8 -*-

import sys
import xbmc


import os
from urlparse import parse_qsl
from datetime import datetime
import xbmcgui
import xbmcplugin
import xbmcaddon
import random

from lxml import html 
import requests
import urllib2
import json
import time



__addon__ = 'plugin.video.vodtvp'
__settings__ = xbmcaddon.Addon(__addon__)
     
# Get the plugin url in plugin:// notation.
__url__ = sys.argv[0]
# Get the plugin handle as an integer number.
__handle__ = int(sys.argv[1])

# HTTP constants
user_agent = ['Mozilla/5.0 (Windows NT 6.1; Win64; x64)',
                'AppleWebKit/537.36 (KHTML, like Gecko)',
                'Chrome/55.0.2883.87',
                'Safari/537.36']

http_headers = {'User-Agent':user_agent[0], 
            'Accept':"text/html", 
            'Accept-Encoding':'identity', 
            'Accept-Language':'en-US,en;q=0.8',
            'Accept-Charset':'utf-8'
            }
http_timeout = 30


BASE_URL = 'https://vod.tvp.pl'
PLAYER_URL = '/sess/tvplayer.php'
PLAYER2_URL = '/sess/TVPlayer2/api.php'

DEFAULT_THUMB_URL = 'https://s.tvp.pl/files/vod.tvp.pl/img/favicon/mstile-70x70.png'
THUMBS_DIR = './thumbs/'

LIST_SORT_ORDER = '?order=titleAZ&gc=4&page='
EPISODES_SORT_ORDER = '?order=oldest&sezon='

BLACK_VIDEO_URL = 'https://s.tvp.pl/files/tvplayer/video/black-1280x720-v1.mp4'

ADDON_NAME = 'VOD.TVP.pl'

CATEGORIES = {}

SERIES = {}
#'Low', 'Medium', 'High':
RESOLUTIONS = { '0': 820000, '1': 5420000, '2': 9100000 }
#820000,590000,820000,1250000,1750000,2850000,5420000,9100000

max_resolution = __settings__.getSetting('resolution')

MAX_BITRATE = RESOLUTIONS[max_resolution]

format="%d%H"
now = datetime.now()

SUB_SESSION_ID = now.strftime(format)

def log_error(txt):
    log(txt, 'error')
def log_notice(txt):
    log(txt, 'notice')
def log(txt, level='debug'):
    #Write text to Kodi log file.
    levels = {
        'debug': xbmc.LOGDEBUG,
        'error': xbmc.LOGERROR,
        'notice': xbmc.LOGNOTICE
        }
    logLevel = levels.get(level, xbmc.LOGDEBUG)

    message = '%s: %s' % (ADDON_NAME, txt)
    #log: off
    #xbmc.log(msg=message, level=logLevel)

def get_request_url( url, params={} ):
    log_notice("get_request_url( %s, %s ):" % (url, params))

    r = requests.get(url, params=params, headers=http_headers, timeout=http_timeout)
    if r.status_code != requests.codes.ok: # Uh-oh!
        log_error("Error: %s: %s" % (r.status_code, url))
        return
    #save_cookies_lwp(r.cookies)

    return r

def check_url_type(url_to_check):
    """
    check type of page requested
    :param url_to_check: str
    :return: obj: content_type

    content_type['url']: page url (can be modified)
    content_type['type']: type of content, one of:
                    listing : create page listing
                    play    : play video
                    film    : pojedynczy film
                    series  : odcinki serialu
                    subcategories : create list of subcategories
    content_type['data']: page data (if was readed)
    """
    log_notice( "check_url_type( %s )" % url_to_check)

    page_parts = url_to_check.split("/")

    page_type = page_parts[1].strip()

    if page_parts[len(page_parts)-1] == 'video':
            page_type = 'sezon'

    log_notice(str(len(page_parts)) + ", " + page_type)

    content_type = {
        'type': 'listing',
        'url': url_to_check,
    }

    if page_type == 'sezon':
        #episodes
        content_type['type'] = 'series'
        return content_type
    #ok
    if page_type == 'sub-category':
        #listing
        return content_type

    r = get_request_url ( BASE_URL + url_to_check )

    data = html.fromstring(r.content)

    #ok
    if page_type == 'category':
        #listing or subcategory
        # szukam podkategorii
        
        xdata = data.xpath('//div[@class="sliderOneRow category loader"]/div[@class="item"]')
        if len(xdata) > 0:
            content_type['type'] = 'subcategories'
            content_type['data'] = data

        return content_type

    if page_type == 'website':
        #listing, episodes or video
        # episodes with or without seasons

        xdata = data.xpath('//section[@id="eposodeSeries"]/div/h2')

        if len(xdata) > 0:
            #epizody serialu
            links = list(xdata[0].iter("a"))
            #czy mamy epizody
            if len(links) > 0:
                href = links[0].attrib["href"]

                log_notice ( "czy mamy href ? : " + href)
                content_type['type'] = 'series'
                content_type['url'] = href
                #check have seasons ?
                sdata = data.xpath('//div[@class="dropdown dropdownSortBox"]/ul[@class="dropdown-menu"]/li/a')
                if len(sdata)>0:
                    listli = list(sdata)
                    content_type['type'] = 'seasons'
                    content_type['data'] = sdata

                return content_type

        xdata = data.xpath('//div[@class="website--wrapper--play"]/a[@class="website--wrapper--circle"]')

        #log_notice("jest circle ?:" + str(len(xdata)))
        if len(xdata) > 0:
            #pojedynczy film
            links = list(xdata[0].iter("a"))
            href = links[0].attrib["href"]

            title =  'title'
            tdata = data.xpath('//head/meta[@property="og:title"]')
            if len(tdata) > 0:
                ltitle = list(tdata[0].iter("meta"))

                title = ltitle[0].attrib["content"]
            
            description = 'description'
            ddata = data.xpath('//head/meta[@property="og:description"]')
            if len(tdata) > 0:
                ldesc = list(ddata[0].iter("meta"))

                description = ldesc[0].attrib["content"]

            #<meta property="og:description" content="
            content_type['type'] = 'film'
            content_type['url'] = href
            content_type['title'] = title
            content_type['description'] = description

    log_notice("type: "+ content_type['type'] + ", url: " + content_type['url'] )

    return content_type

def get_categories():
    """
    Get the list of video categories.
    :return: list
    """

    log_notice("get_categories()")
    
    page = get_request_url(BASE_URL)

    root = html.fromstring(page.content)
    data = root.xpath('//div[@class="subMenu"]/ul/li/a')

    for i in range(len(data)):
        links = list(data[i].iter("a"))
        for l in links:
            href = l.attrib["href"]
            if (href[0] == '/'):
                real_name = l.text.strip().encode('utf-8')
                name = real_name.upper()

                #thumbs from page(one of sliding)
                thumb = DEFAULT_THUMB_URL
                
                logo = thumb
                saved_logo = '%s.png' % ( real_name)
                if os.path.isfile(saved_logo):
                    logo = saved_logo

                #create tree category/sub-category
                CATEGORIES[name] = [{
                    'category_url': href, 
                    'thumb': thumb,
                    'logo': logo
                    }]

    return CATEGORIES.keys()
def list_categories():
    """
    Create the list of video categories in the Kodi interface.
    :return: None
    """
    log_notice("list_categories()")
    # Get video categories
    categories = get_categories()
    # Create a list for our items.
    listing = []
    # Iterate through categories
    for category in categories:
        # Create a list item with a text label and a thumbnail image.
        #list_item = xbmcgui.ListItem(label=category, thumbnailImage=VIDEOS[category][0]['thumb'])
        list_item = xbmcgui.ListItem(label=category, thumbnailImage=CATEGORIES[category][0]['thumb'])
        category_url = thumbnailImage=CATEGORIES[category][0]['category_url']
        # Set a fanart image for the list item.
        # Here we use the same image as the thumbnail for simplicity's sake.
        #list_item.setProperty('fanart_image', VIDEOS[category][0]['thumb'])
        # Set additional info for the list item.
        # Here we use a category name for both properties for for simplicity's sake.
        # setInfo allows to set various information for an item.
        # For available properties see the following link:
        # http://mirrors.xbmc.org/docs/python-docs/15.x-isengard/xbmcgui.html#ListItem-setInfo
        #list_item.setInfo('video', {'title': category, 'genre': category})
        # Create a URL for the plugin recursive callback.
        # Example: plugin://plugin.video.example/?action=listing&category=Animals

        url = '{0}?link_url={1}'.format(__url__, category_url)

        # is_folder = True means that this item opens a sub-list of lower level items.
        is_folder = True
        # Add our item to the listing as a 3-element tuple.
        listing.append((url, list_item, is_folder))
    # Add our listing to Kodi.
    # Large lists and/or slower systems benefit from adding all items at once via addDirectoryItems
    # instead of adding one by ove via addDirectoryItem.
    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    # Add a sort method for the virtual folder items (alphabetically, ignore articles)
    xbmcplugin.addSortMethod(__handle__, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(__handle__)

def get_subcategories(category_url, category_data):
    log_notice("get_subcategories(%s, %s)" % (category_url, category_data) )

    tree = category_data
    #checking sub-categories
    data = tree.xpath('//div[@class="sliderOneRow category loader"]/div[@class="item"]/a')

    name = 'NoName'
    thumb = DEFAULT_THUMB_URL
    href = ''

    SUBCATEGORIES = {}
    for j in range(len(data)):
        links = list(data[j].iter("a"))
        for s in links:
            href = s.attrib["href"]
            #looking for sub-category name
            names = list(data[j].iter("h2"))
            for s in names:
                name = s.text.strip().upper().encode('utf-8')
                #looking for sub-category thumb
                imgs = list(data[j].iter("img"))
                for s in imgs:
                    thumb = s.attrib["data-lazy"]

            data2 = tree.xpath('//title')

            page_title = data2[0].text.split("-")[0].strip()

            SUBCATEGORIES[name] = [{
                        'category_url': href,
                        'thumb': thumb,
                        'page_title': page_title
                    }]
    return SUBCATEGORIES
def list_subcategories( category_url, category_data):
    """
    Create the list of video categories in the Kodi interface.
    :return: None
    """
    log_notice("list_subcategories(%s, %s)" % (category_url, category_data))
    # Get video categories
    listing = []
    # Iterate through categories
    subcategories = get_subcategories(category_url, category_data)

    for subcat in subcategories:
        # Create a list item with a text label and a thumbnail image.
        #list_item = xbmcgui.ListItem(label=category, thumbnailImage=VIDEOS[category][0]['thumb'])
        list_item = xbmcgui.ListItem(label=subcat, thumbnailImage=subcategories[subcat][0]['thumb'])

        # Set a fanart image for the list item.
        # Here we use the same image as the thumbnail for simplicity's sake.
        #list_item.setProperty('fanart_image', VIDEOS[category][0]['thumb'])
        # Set additional info for the list item.
        # Here we use a category name for both properties for for simplicity's sake.
        # setInfo allows to set various information for an item.
        # For available properties see the following link:
        # http://mirrors.xbmc.org/docs/python-docs/15.x-isengard/xbmcgui.html#ListItem-setInfo
        #list_item.setInfo('video', {'title': category, 'genre': category})
        # Create a URL for the plugin recursive callback.
        # Example: plugin://plugin.video.example/?action=listing&category=Animals

        category_url = subcategories[subcat][0]['category_url']

        url = '{0}?link_url={1}'.format(__url__, category_url)

        # is_folder = True means that this item opens a sub-list of lower level items.
        is_folder = True
        # Add our item to the listing as a 3-element tuple.
        listing.append((url, list_item, is_folder))
    # Add our listing to Kodi.
    # Large lists and/or slower systems benefit from adding all items at once via addDirectoryItems
    # instead of adding one by ove via addDirectoryItem.
    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    # Add a sort method for the virtual folder items (alphabetically, ignore articles)
    xbmcplugin.addSortMethod(__handle__, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(__handle__)

def get_listing( listing_url ):
    """
    Get the list of videofiles/streams.
    Here you can insert some parsing code that retrieves
    the list of videostreams in a given category from some site or server.
    :param category: str
    :return: list
    """
    log_notice("get_listing(%s)" % (listing_url))

    pagedata = get_request_url(BASE_URL + listing_url + LIST_SORT_ORDER + '1')

    root = html.fromstring(pagedata.content)
    data = root.xpath('//section[@class="pagePagination text-center"]')
    sections = list(data[0].iter("section"))
    pages = 1
    pages = int(sections[0].attrib["data-total"])
    LISTING = {}
    
    page = 1
    while page <= pages:
        data = root.xpath('//div[@class="strefa-abo__item "]/a')

        for i in range(len(data)):
            links = list(data[i].iter("a"))

            href = links[0].attrib["href"]

            shref = href.split(",")
            content_id = shref[len(shref)-1]
            isAboContent = list(data[i].iter("div"))[0].attrib["data-paylabel"].encode('utf-8')
            
            if isAboContent == '':

                jsonData = list(data[i].iter("div"))[0].attrib["data-hover"].encode('utf-8')

                title = list(data[i].iter("h3"))[0].text.strip().encode('utf-8')

                thumb = list(data[i].iter("img"))[0].attrib["src"]

                #log_notice("Page: " + str(page) + " : " + title + " : " + href + " : " + thumb)

                LISTING[content_id] = {
                    'title': title,
                    'thumb': thumb,
                    'url': href,
                    'json_data': jsonData,
                }

        # read next page
        page = page + 1
        if pages >= page:
            pagedata = get_request_url(BASE_URL + listing_url + LIST_SORT_ORDER + str(page))
            root = html.fromstring(pagedata.content)
    return LISTING
def list_listing( listing_url):
    """
    Create the list of playable videos in the Kodi interface.
    :param category: str
    :return: None
    """
    log_notice("list_listing(%s)" %  (listing_url))
    # Get the list of videos in the category.
    videos = get_listing( listing_url )

    # Create a list for our items.
    listing = []
    # Iterate through videos.
    for video in videos:
        #log_notice(videos[video]['json_data'])
        # Create a list item with a text label and a thumbnail image.
        list_item = xbmcgui.ListItem(label=videos[video]['title'], thumbnailImage=videos[video]['thumb'])
        # Set a fanart image for the list item.
        # Here we use the same image as the thumbnail for simplicity's sake.
        list_item.setProperty('fanart_image', videos[video]['thumb'])
        # Set additional info for the list item.

        # is_folder = False means that this item won't open any sub-list.
        is_folder = True
        vdata = json.loads( videos[video]['json_data'] )

        list_item.setInfo('video', {
            'title': videos[video]['title'],
            'plot': vdata['description'],
            })
        item_url = videos[video]['url']

        # Set 'IsPlayable' property to 'true'.
        # This is mandatory for playable items!
        list_item.setProperty('IsPlayable', 'true')
        # Create a URL for the plugin recursive callback.
        # Example: plugin://plugin.video.example/?action=play&video=http://www.vidsplay.com/vids/crab.mp4
        url = '{0}?link_url={1}&thumb_url={2}'.format(__url__, item_url, videos[video]['thumb'])
        # Add the list item to a virtual Kodi folder.

        #log_notice("url:" + url + ":" + str(is_folder))
        # Add our item to the listing as a 3-element tuple.
        listing.append((url, list_item, is_folder))
    # Add our listing to Kodi.
    # Large lists and/or slower systems benefit from adding all items at once via addDirectoryItems
    # instead of adding one by ove via addDirectoryItem.
    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    # Add a sort method for the virtual folder items (alphabetically, ignore articles)
    xbmcplugin.addSortMethod(__handle__, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(__handle__)

def get_episodes( episodes_url, season = '0'):
    """
    Get the list of videofiles/streams.
    Here you can insert some parsing code that retrieves
    the list of videostreams in a given category from some site or server.
    :param category: str
    :return: list
    """
    log_notice("get_episodes(%s, %s)" % (episodes_url, season) )

    page = 1
    datapage = get_request_url(BASE_URL + episodes_url + EPISODES_SORT_ORDER + season + '&page=' + str(page))

    root = html.fromstring(datapage.content)
    data = root.xpath('//section[@class="pagePagination text-center"]')
    sections = list(data[0].iter("section"))
    pages = 1
    pages = int(sections[0].attrib["data-total"])
    VIDEOS = {}
    while page <= pages:
        data = root.xpath('//div[@class="strefa-abo__item "]/a[@class="strefa-abo__item-link"]')

        for i in range(len(data)):
            links = list(data[i].iter("a"))
            for l in links:
                href = l.attrib["href"]
            
            shref = href.split(",")
            video_id = shref[len(shref)-1]

            jsonData = list(data[i].iter("div"))[0].attrib["data-hover"].encode('utf-8')

            title = list(data[i].iter("h3"))[0].text.strip().encode('utf-8')

            stitle = list(data[i].iter("h4"))


            # element h4
            if len(stitle) > 0:
                #text h4
                h4text = stitle[0].text
                if h4text is not None:
                    #log_notice("h4text: " + h4text.encode('utf-8'))
                    #title = title + ":" + h4text.encode('utf-8').strip()
                    title = h4text.encode('utf-8').strip()

            thumb = list(data[i].iter("img"))[0].attrib["src"]

            #log_notice("Page: " + str(page) + " : " + title + " : " + href + " : " + thumb)

            VIDEOS[video_id] = {
                'title': title,
                'thumb': thumb,
                'video_url': href,
                'json_data': jsonData,
                'is_folder': False
            }

        # read next page
        page = page + 1
        if pages >= page:
            datapage = get_request_url( BASE_URL + episodes_url + EPISODES_SORT_ORDER + season + '&page=' + str(page))
            root = html.fromstring(datapage.content)

    return VIDEOS

def list_episodes( episodes_url, season = '0'):
    """
    Create the list of playable videos in the Kodi interface.
    :param category: str
    :return: None
    """
    log_notice("list_episodes(%s, %s)" % ( episodes_url, season) )
    # Get the list of videos in the category.
    videos = get_episodes( episodes_url, season)

    # Create a list for our items.
    listing = []
    # Iterate through videos.
    for video in videos:
        #log_notice(videos[video]['json_data'])
        # Create a list item with a text label and a thumbnail image.
        list_item = xbmcgui.ListItem(label=videos[video]['title'], thumbnailImage=videos[video]['thumb'])
        # Set a fanart image for the list item.
        # Here we use the same image as the thumbnail for simplicity's sake.
        list_item.setProperty('fanart_image', videos[video]['thumb'])
        # Set additional info for the list item.

        vdata = json.loads( videos[video]['json_data'] )

        list_item.setInfo('video', {
            'title': videos[video]['title'],
            'plot': vdata['description'],
            })
        
        action = 'play'

        # Set 'IsPlayable' property to 'true'.
        # This is mandatory for playable items!
        list_item.setProperty('IsPlayable', 'true')
        # Create a URL for the plugin recursive callback.
        # Example: plugin://plugin.video.example/?action=play&video=http://www.vidsplay.com/vids/crab.mp4
        url = '{0}?action={1}&link_url={2}'.format(__url__, action, videos[video]['video_url'])
        # Add the list item to a virtual Kodi folder.
        # is_folder = False means that this item won't open any sub-list.
        is_folder = False
        # Add our item to the listing as a 3-element tuple.
        listing.append((url, list_item, is_folder))
    # Add our listing to Kodi.
    # Large lists and/or slower systems benefit from adding all items at once via addDirectoryItems
    # instead of adding one by ove via addDirectoryItem.
    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    # Add a sort method for the virtual folder items (alphabetically, ignore articles)
    xbmcplugin.addSortMethod(__handle__, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(__handle__)
    
def list_one(one_data):
    log_notice("list_one(%s)" % ( one_data) )
    # Get the list of videos in the category.
    # Create a list for our items.
    listing = []
    list_item = xbmcgui.ListItem(label=one_data['title'], thumbnailImage=one_data['thumb_url'])
    list_item.setProperty('fanart_image', one_data['thumb_url'])
    list_item.setInfo('video', {
        'title': one_data['title'],
        'plot': one_data['description'],
    })
    list_item.setProperty('IsPlayable', 'true')
    is_folder = False
    url = '{0}?action=play&link_url={1}'.format(__url__, one_data['url'])
    listing.append((url, list_item, is_folder))

    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    xbmcplugin.endOfDirectory(__handle__)
    
def get_seasons( seasons_data ):
    """
    Get the list of videofiles/streams.
    Here you can insert some parsing code that retrieves
    the list of videostreams in a given category from some site or server.
    :param category: str
    :return: list
    """
    log_notice("get_seasons(%s)" % seasons_data)

    SEASONS = {}

    for i in range(len(seasons_data)):
        links = list(seasons_data[i].iter("a"))
        for l in links:
            href = l.attrib["href"]
            title = l.text.strip().encode('utf-8')
            #log_notice(href)
            from_params = href.find("?") + 1
            url = href[:from_params - 1]
            params = dict(parse_qsl(href[from_params:]))
            #log_notice(url)
            #log_notice(params)
            SEASONS[title] = {
                'href': url,
                'season': params['sezon']
            }
    #log_notice(SEASONS)

    return SEASONS
def list_seasons( seasons_data, thumb_url):
    """
    Create the list of playable videos in the Kodi interface.
    :param category: str
    :return: None
    """
    log_notice("list_seasons(%s,%s)" % ( seasons_data, thumb_url ))
    # Get the list of videos in the category.
    seasons = get_seasons( seasons_data )

    # Create a list for our items.
    listing = []
    # Iterate through seasons.
    for season in seasons:
        #log_notice(videos[video]['json_data'])
        # Create a list item with a text label and a thumbnail image.
        list_item = xbmcgui.ListItem(label=season, thumbnailImage=thumb_url)
        # Set a fanart image for the list item.
        # Here we use the same image as the thumbnail for simplicity's sake.
        list_item.setProperty('fanart_image', thumb_url)
        # Set additional info for the list item.

        list_item.setInfo('video', {
            'title': season
            })
        
        action = 'series'

        # Set 'IsPlayable' property to 'true'.
        # This is mandatory for playable items!

        # Create a URL for the plugin recursive callback.
        # Example: plugin://plugin.video.example/?action=play&video=http://www.vidsplay.com/vids/crab.mp4
        url = '{0}?action={1}&link_url={2}&season={3}'.format(__url__, action, seasons[season]['href'], seasons[season]['season'])

        # Add the list item to a virtual Kodi folder.
        # is_folder = False means that this item won't open any sub-list.
        is_folder = True
        # Add our item to the listing as a 3-element tuple.
        listing.append((url, list_item, is_folder))
    # Add our listing to Kodi.
    # Large lists and/or slower systems benefit from adding all items at once via addDirectoryItems
    # instead of adding one by ove via addDirectoryItem.
    xbmcplugin.addDirectoryItems(__handle__, listing, len(listing))
    # Add a sort method for the virtual folder items (alphabetically, ignore articles)
    xbmcplugin.addSortMethod(__handle__, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    # Finish creating a virtual folder.
    xbmcplugin.endOfDirectory(__handle__)

def get_video_url(website_url):
    log_notice("get_video_url(%s)" % website_url)

    video_url = ''

    timestamp = int(time.time() * 1000)

    URL = BASE_URL + website_url
    vr = get_request_url(URL)

    hdata = html.fromstring(vr.content)
    xdata = hdata.xpath('//div[@id="JS-TVPlayer2-Wrapper"]')[0]
    
    ldata = list(xdata.iter("div"))[0]

    URL = BASE_URL + PLAYER_URL
    params = {
        'object_id': ldata.attrib["data-video-id"],
        'dump': 'json',
        'template': '',
        'check_premium_access': 1
    }
    jr = get_request_url(URL, params)

    jdata = json.loads( jr.content.encode('utf-8')  )

    URL = BASE_URL + PLAYER2_URL
    params = {
        'id': ldata.attrib["data-video-id"],
        '@method': 'getTvpConfig',
        '@callback': '__tpJSON' + SUB_SESSION_ID + 'T' + str( timestamp )
    }
    pr = get_request_url(URL, params)

    content = pr.content.encode('utf-8')

    start_src = content.find("(")+1
    stop_src = content.rfind(")")
    len_src = len(content)

    jcontent = content[start_src:stop_src]

    jdata = json.loads( jcontent )

    this_bitrate = 0
    lowest_bitrate = 0
    lowest_video_url = ''
    for file in jdata['content']['files']:
        quality = file['quality']
        if quality != 0:
            if  ( quality['bitrate'] < lowest_bitrate ) or ( lowest_bitrate == 0):
                lowest_bitrate = quality['bitrate']
                lowest_video_url = file['url']
            if (quality['bitrate'] > this_bitrate) and (quality['bitrate'] <= MAX_BITRATE) :
                this_bitrate = quality['bitrate'] 
                video_url = file['url']

    if video_url == '':
        video_url = lowest_video_url

    if video_url == '':
        video_url = BLACK_VIDEO_URL

    return video_url

def play_video(video_url):
    """
    Play a video by the provided path.
    :param path: str
    :return: None
    """
    log_notice("play_video(%s)" % video_url)

    # Create a playable item with a path to play.
    video_url = get_video_url(video_url)
    #video_path = PLAYER_URL + video_id
    log_notice("Video url:" + video_url)
    play_item = xbmcgui.ListItem(path=video_url)
    # Pass the item to the Kodi player.
    xbmcplugin.setResolvedUrl(__handle__, True, listitem=play_item)

def router(paramstring):
    """
    Router function that calls other functions
    depending on the provided paramstring
    :param paramstring:
    :return:
    """
    log_notice("router(%s)" % paramstring)
    # Parse a URL-encoded paramstring to the dictionary of
    # {<parameter>: <value>} elements
    params = dict(parse_qsl(paramstring[1:]))
    log_notice(params)
    # Check the parameters passed to the plugin
    if params:
        if 'action' in params:
            if params['action'] == 'play':
                # Play a video from a provided URL.
                log_notice("PLAY")
                play_video(params['link_url'])
                params['link_url'] = ''
        if params['link_url'] != '':
            content_type = check_url_type( params['link_url'] )
            log_notice ( content_type )

            if content_type['type'] == 'film':
                if 'thumb_url' in params:
                    content_type['thumb_url'] = params['thumb_url']
                list_one(content_type)

            if content_type['type'] == 'subcategories':
                list_subcategories( content_type['url'], content_type['data'] )

            if content_type['type'] == 'series':
                if 'season' in params:
                    list_episodes( content_type['url'], params['season'])
                else:
                    list_episodes( content_type['url'])

            if content_type['type'] == 'seasons':
                # Display the list of videos in a provided category.
                thumb_url = DEFAULT_THUMB_URL
                if 'thumb_url' in params:
                    thumb_url = params['thumb_url']
                list_seasons( content_type['data'], thumb_url)

            if content_type['type'] == 'listing':
                list_listing( content_type['url'] )
    else:
        # If the plugin is called from Kodi UI without any parameters,
        # display the list of video categories
        list_categories()

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    router(sys.argv[2])

