# duckduckgo.py - Library for querying the DuckDuckGo API
#
# Copyright (c) 2010 Michael Stephens <me@mikej.st>
# Copyright (c) 2012-2013 Michael Smith <crazedpsyc@gshellz.org>
# Copyright (c) 2017 Members of the Programming Server
#
# See LICENSE for terms of usage, modification and redistribution.

from typing import Tuple
import logging
import urllib.parse

from ratelimit import rate_limited
import aiohttp

from ._version import __version__
from .models import Results

DEFAULT_USER_AGENT = f'python-duckduckgo {__version__}'
DEFAULT_PRIORITIES = ('answer', 'abstract', 'related.0', 'definition')

logger = logging.getLogger('duckduckgo')

@rate_limited(1)
async def query(q: str,
                useragent: str = DEFAULT_USER_AGENT,
                safesearch: bool = True,
                html: bool = False,
                meanings: bool = True,
                **kwargs) -> Results:
    """
    Query DuckDuckGo, returning a Results object.

    The API is queried asynchronously, and redirects are followed.

    Keyword arguments:
    useragent: UserAgent to use while querying. Default: "python-duckduckgo <version>" (str)
    safesearch: True for on, False for off. Default: True (bool)
    html: True to allow HTML in output. Default: False (bool)
    meanings: True to include disambiguations in results (bool)
    Any other keyword arguments are passed directly to DuckDuckGo as URL params.
    """

    logger.info(f"Performing DDG query: '{q}'")
    logger.debug(f"Safesearch: {safesearch}")
    logger.debug(f"HTML: {html}")
    logger.debug(f"Meanings: {meanings}")

    safesearch = '1' if safesearch else '-1'
    html = '0' if html else '1'
    meanings = '0' if meanings else '1'
    params = {
        'q': q,
        'o': 'json',
        'kp': safesearch,
        'no_redirect': '1',
        'no_html': html,
        'd': meanings,
    }
    params.update(kwargs)
    logger.debug(f"Full parameters: {params}")

    encparams = urllib.parse.urlencode(params)
    url = f'http://api.duckduckgo.com/?{encparams}'

    async with aiohttp.ClientSession() as cs:
        async with cs.get(url, headers={'User-Agent': useragent}) as req:
            response = await req.json(content_type='application/x-javascript')
            if response is None:
                logger.error("Response is 'None'")
                raise ValueError("Failed to decode JSON response")

    logger.debug("Response is {response}")
    return Results(response)

async def get_zci(q: str,
        web_fallback: bool = True,
        priority: Tuple[str] = DEFAULT_PRIORITIES,
        urls: bool = True,
        **kwargs) -> str:
    '''A helper method to get a single (and hopefully the best) ZCI result.
    priority=list can be used to set the order in which fields will be checked for answers.
    Use web_fallback=True to fall back to grabbing the first web result.
    passed to query. This method will fall back to 'Sorry, no results.'
    if it cannot find anything.'''

    logger.info(f"Performing DDG ZCI: '{q}'")
    logger.debug(f"Web fallback: {web_fallback}")
    logger.debug(f"Use URLs: {urls}")

    ddg = await query(f'\\{q}', **kwargs)
    response = ''

    for p in priority:
        ps = p.split('.')
        type = ps[0]
        index = int(ps[1]) if len(ps) > 1 else None

        result = getattr(ddg, type)
        if index is not None:
            if not hasattr(result, '__getitem__'):
                logger.error("Result is not indexable!")
                raise TypeError(f'{type} field is not indexable')

            result = result[index] if len(result) > index else None

        if not result:
            continue
        elif result.text:
            logger.debug(f"Result has text: {result.text}")
            response = result.text

            if getattr(result, 'url', None) and urls:
                logger.debug(f"Result has url: {result.url}")
                response += f' ({result.url})'

            break

    # If there still isn't anything, try to get the first web result
    logger.debug("Trying web fallback...")
    if not response and web_fallback:
        if ddg.redirect.url:
            response = ddg.redirect.url

    # Final fallback
    logger.info("No results!")
    if not response:
        response = 'Sorry, no results.'

    logger.debug(f"Final response: {response!r}")
    return response