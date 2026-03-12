'''
Function:
    Implementation of FiveSingMusicClient: https://5sing.kugou.com/index.html
Author:
    Zhenchao Jin
WeChat Official Account (微信公众号):
    Charles的皮卡丘
'''
import copy
from .base import BaseMusicClient
from urllib.parse import urlencode
from rich.progress import Progress
from ..utils import legalizestring, byte2mb, resp2json, usesearchheaderscookies, safeextractfromdict, extractdurationsecondsfromlrc, seconds2hms, cleanlrc, SongInfo


'''FiveSingMusicClient'''
class FiveSingMusicClient(BaseMusicClient):
    source = 'FiveSingMusicClient'
    def __init__(self, **kwargs):
        super(FiveSingMusicClient, self).__init__(**kwargs)
        self.default_search_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        }
        self.default_download_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        }
        self.default_headers = self.default_search_headers
        self._initsession()
    '''_constructsearchurls'''
    def _constructsearchurls(self, keyword: str, rule: dict = None, request_overrides: dict = None):
        # init
        rule, request_overrides = rule or {}, request_overrides or {}
        # search rules
        default_rule = {'keyword': keyword, 'sort': 1, 'page': 1, 'filter': 0, 'type': 0}
        default_rule.update(rule)
        # construct search urls based on search rules
        base_url = 'http://search.5sing.kugou.com/home/json?'
        search_urls, page_size, count = [], self.search_size_per_page, 0
        while self.search_size_per_source > count:
            page_rule = copy.deepcopy(default_rule)
            page_rule['page'] = int(count // page_size) + 1
            search_urls.append(base_url + urlencode(page_rule))
            count += page_size
        # return
        return search_urls
    '''_search'''
    @usesearchheaderscookies
    def _search(self, keyword: str = '', search_url: str = '', request_overrides: dict = None, song_infos: list = [], progress: Progress = None, progress_id: int = 0):
        # init
        request_overrides = request_overrides or {}
        # successful
        try:
            # --search results
            resp = self.get(search_url, **request_overrides)
            resp.raise_for_status()
            search_results = resp2json(resp)['list']
            for search_result in search_results:
                # --download results
                if not isinstance(search_result, dict) or ('songId' not in search_result) or ('typeEname' not in search_result): continue
                song_info = SongInfo(source=self.source)
                params = {'songid': str(search_result['songId']), 'songtype': search_result['typeEname']}
                try:
                    resp = self.get('http://mobileapi.5sing.kugou.com/song/getSongUrl', params=params, **request_overrides)
                    resp.raise_for_status()
                    download_result: dict = resp2json(resp)
                    if str(download_result['code']) not in ('1000',): continue
                except:
                    continue
                for quality in ['sq', 'hq', 'lq']:
                    download_url = safeextractfromdict(download_result, ['data', f'{quality}url'], '') or safeextractfromdict(download_result, ['data', f'{quality}url_backup'], '')
                    if not download_url: continue
                    song_info = SongInfo(
                        raw_data={'search': search_result, 'download': download_result, 'lyric': {}}, source=self.source, song_name=legalizestring(safeextractfromdict(search_result, ['songName'], None)),
                        singers=legalizestring(safeextractfromdict(search_result, ['singer'], None)), album='NULL', ext=safeextractfromdict(download_result, ['data', f'{quality}ext'], 'mp3') or 'mp3',
                        file_size_bytes=int(float(safeextractfromdict(download_result, ['data', f'{quality}size'], 0) or 0)), file_size=byte2mb(safeextractfromdict(download_result, ['data', f'{quality}size'], 0)),
                        identifier=search_result['songId'], duration='-:-:-', lyric=None, cover_url=safeextractfromdict(download_result, ['data', 'user', 'I'], None), download_url=download_url, 
                        download_url_status=self.audio_link_tester.test(download_url, request_overrides),
                    )
                    song_info.download_url_status['probe_status'] = self.audio_link_tester.probe(song_info.download_url, request_overrides)
                    song_info.file_size = song_info.download_url_status['probe_status']['file_size']
                    song_info.ext = song_info.download_url_status['probe_status']['ext'] if (song_info.download_url_status['probe_status']['ext'] and song_info.download_url_status['probe_status']['ext'] not in ('NULL',)) else song_info.ext
                    if song_info.with_valid_download_url: break
                if not song_info.with_valid_download_url: continue
                # --lyric results
                params = {'songid': str(search_result['songId']), 'songtype': search_result['typeEname'], 'songfields': '', 'userfields': ''}
                try:
                    resp = self.get('http://mobileapi.5sing.kugou.com/song/newget', params=params, **request_overrides)
                    resp.raise_for_status()
                    lyric_result: dict = resp2json(resp)
                    lyric = cleanlrc(safeextractfromdict(lyric_result, ['data', 'dynamicWords'], 'NULL')) or 'NULL'
                    song_info.album = legalizestring(safeextractfromdict(lyric_result, ['data', 'albumName'], None))
                    song_info.cover_url = safeextractfromdict(lyric_result, ['data', 'user', 'I'], None)
                    song_info.duration = seconds2hms(extractdurationsecondsfromlrc(lyric))
                except:
                    lyric_result, lyric = {}, 'NULL'
                # --update song_info
                song_info.raw_data['lyric'] = lyric_result
                song_info.lyric = lyric
                # --append to song_infos
                song_infos.append(song_info)
                # --judgement for search_size
                if self.strict_limit_search_size_per_page and len(song_infos) >= self.search_size_per_page: break
            # --update progress
            progress.update(progress_id, description=f"{self.source}.search >>> {search_url} (Success)")
        # failure
        except Exception as err:
            progress.update(progress_id, description=f"{self.source}.search >>> {search_url} (Error: {err})")
        # return
        return song_infos