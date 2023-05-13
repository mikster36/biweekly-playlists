import pylast
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
from torchvision.transforms.functional import adjust_hue
from difflib import SequenceMatcher
from PIL import Image
from io import BytesIO
import credentials as c
import random
import base64
import time
import re

# constants
LASTFM_API_KEY: str = c.LASTFM_API_KEY
LASTFM_API_SECRET: str = c.LASTFM_API_SECRET
LASTFM_MY_ACCOUNT: str = c.LASTFM_MY_ACCOUNT
LASTFM_MY_PASSWORD: str = pylast.md5(c.LASTFM_MY_PASSWORD)
LASTFM_C_ACCOUNT: str = c.LASTFM_C_ACCOUNT
LASTFM_M_ACCOUNT: str = c.LASTFM_M_ACCOUNT
SPOTIFY_CLIENT_ID: str = c.SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET: str = c.SPOTIFY_CLIENT_SECRET
SPOTIFY_USERNAME: str = c.SPOTIFY_USERNAME
REDIRECT_URI: str = "http://localhost:8080/"
SCOPES: list = ["playlist-modify-public", "user-library-read", "ugc-image-upload"]
PLAYLIST_COVER_PATH: str = "playlist_cover.jpg"
COUNTER_PATH = "counter.txt"
LAST_WEEK_TRACKS_PATH = "last_week.txt"


class Track:

    def __init__(self,
                 title: str = None,
                 artist: str = None,
                 uri: str = None):
        if uri is not None:
            search = my_spotify.search(q=uri, type="track", limit=1, market="US")
            self.title = search["tracks"]["items"][0]["name"]
            self.artist = search["tracks"]["items"][0]
            return
        self.title = clean(title, filter="track")
        self.artist = clean(artist, filter="artist")
        self.spotify_info = self.get_spotify_info()

    def __str__(self):
        return f"{self.title}[][][]{self.artist}"

    def get_spotify_info(self):
        return my_spotify.search(q=self.title + " " + self.artist,
                                 type="track", limit=1, market="US")

    def get_uri(self):
        return self.spotify_info["tracks"]["items"][0]["uri"]

    def spotify_search_success(self):
        return SequenceMatcher(None,
                               self.artist.lower(),
                               self.spotify_info["tracks"]["items"][0]["artists"][0]["name"].lower()).ratio() * 0.5 \
               + SequenceMatcher(None,
                                 self.title.lower(),
                                 self.spotify_info["tracks"]["items"][0]["name"].lower()).ratio() * 0.5 >= 0.8


# authorization for last.fm and Spotify
def auth():
    global my_spotify
    network = pylast.LastFMNetwork(api_key=LASTFM_API_KEY, api_secret=LASTFM_API_SECRET,
                                   username=LASTFM_MY_ACCOUNT, password_hash=LASTFM_MY_PASSWORD)
    my_user: pylast.User = pylast.User(user_name=LASTFM_MY_ACCOUNT, network=network)
    c_user: pylast.User = pylast.User(user_name=LASTFM_C_ACCOUNT, network=network)
    m_user: pylast.User = pylast.User(user_name=LASTFM_M_ACCOUNT, network=network)
    users: list = [my_user, c_user, m_user]
    my_spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=c.SPOTIFY_CLIENT_ID,
                                                           client_secret=c.SPOTIFY_CLIENT_SECRET,
                                                           redirect_uri=REDIRECT_URI,
                                                           scope=SCOPES))
    return users


def add_to_playlist(counter: int, tracks: list):
    my_spotify.user_playlist_create(user=c.SPOTIFY_USERNAME,
                                    name=f"boolinmigster {int(counter / 2)}")
    time.sleep(2)
    playlist_uri = my_spotify.user_playlists(user=c.SPOTIFY_USERNAME, limit=1)["items"][0]["uri"]
    my_spotify.playlist_add_items(
        playlist_id=playlist_uri,
        items=tracks)
    my_spotify.playlist_upload_cover_image(playlist_id=playlist_uri, image_b64=get_image(PLAYLIST_COVER_PATH))


def clean(item: str, filter: str):
    if filter.lower() == "artist":
        if "and" in item:
            item = item[:item.index("and")]
        if "&" in item:
            item = item[:item.index("&")]
        return item.rstrip()
    if filter.lower() == "track":
        if re.search("[(].+[)]$", item) and "remix" not in item.lower():
            item = item[:item.index("(")]
        return item.rstrip()
    raise Exception("Filter must be track or artist")


def contains_duplicates(data: list, filter: str):
    seen = set()
    for track in data:
        if track.item.artist not in seen:
            if filter == "artist":
                seen.add(track.item.artist)
            elif filter == "track":
                seen.add(track.item.title)
    return len(seen) != len(data)


def get_image(file_path: str):
    img = Image.open(file_path)
    img = adjust_hue(img=img, hue_factor=random.random() - 0.5)
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue())


def get_top_tracks(
        user: pylast.User,
        period,
        limit,
        read_last_week=False,
        last_week_tracks=None):
    c = limit
    data_out = []
    ignores = set()
    lastfm_data: list = remove_duplicates(user.get_top_tracks(period=period, limit=c), filter="artist")
    for data in lastfm_data:
        temp = Track(title=str(data.item.title), artist=str(data.item.artist))
        if not temp.spotify_search_success(): ignores.add(data)
    while len(set(lastfm_data).difference(ignores)) < limit and c != 100:
        for data in lastfm_data:
            temp = Track(title=str(data.item.title), artist=str(data.item.artist))
            if (read_last_week and clean(data.item.title, filter="track") in get_tracks(last_week_tracks)) \
                    or not temp.spotify_search_success():
                ignores.add(data)
            del temp
        c += 1
        lastfm_data = remove_duplicates(user.get_top_tracks(period=period, limit=c), filter="artist")
    lastfm_data = list(set(lastfm_data).difference(ignores))
    for track in lastfm_data:
        data_out.append(Track(title=str(track.item.title), artist=str(track.item.artist)))
    return data_out


def get_tracks(data: list):
    return_data = [str] * len(data)
    for i, j in enumerate(data):
        return_data[i] = j[:j.index("[][][]")]
    return return_data


def remove_duplicates(data: list, filter: str):
    seen = set()
    seen_out = set()
    for track in data:
        if filter == "artist" and track.item.artist not in seen:
            seen.add(track.item.artist)
            seen_out.add(track)
        elif filter == "track" and track.item.title not in seen:
            seen.add(track.item.title)
            seen_out.add(track)
    return list(seen_out)


def run(read_last_week=False, last_weeks_tracks=None):
    global last_file
    users = auth()
    if not read_last_week:
        last_file = open(LAST_WEEK_TRACKS_PATH, "w")
        top_tracks = []
    else:
        top_tracks = [Track(
            title=track[:track.index("[][][]")],
            artist=track[(track.index("[][][]") + 6):]).get_uri() for track in last_weeks_tracks]
    for user in users:
        for track in get_top_tracks(user=user, period=pylast.PERIOD_7DAYS, limit=3,
                                    read_last_week=read_last_week, last_week_tracks=last_weeks_tracks):
            if len(track.spotify_info["tracks"]["items"]) == 0:
                raise Exception(f"{track} not found by Spotify search.")
            top_tracks.append(track.get_uri())
            if not read_last_week: last_file.write(str(track) + "\n")
    random.shuffle(top_tracks)
    if not read_last_week: last_file.close()
    return top_tracks


def main():
    with open(COUNTER_PATH) as f: counter = int(f.read())
    counter += 1
    if counter % 2 == 0:
        with open(LAST_WEEK_TRACKS_PATH) as f: lines = f.readlines()
        lines = [line.rstrip() for line in lines]
        del lines[-1]
        top_tracks = run(read_last_week=True, last_weeks_tracks=lines)
        add_to_playlist(counter=counter, tracks=top_tracks)
    else:
        run()
    with open(COUNTER_PATH, 'w') as f:
        f.write(str(counter))


if __name__ == "__main__":
    main()