import os
import time
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


def spotify_access_token():
    """Usa refresh token para obtener access token de Spotify."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ["SPOTIFY_REFRESH_TOKEN"],
        "client_id": os.environ["SPOTIFY_CLIENT_ID"],
        "client_secret": os.environ["SPOTIFY_CLIENT_SECRET"],
    }
    r = requests.post(SPOTIFY_TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def spotify_playlist_tracks(playlist_id: str):
    """Lee tracks de una playlist de Spotify y devuelve lista de {artist, name}."""
    token = spotify_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    tracks = []
    limit = 100
    offset = 0

    while True:
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        params = {"limit": limit, "offset": offset}
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for it in data.get("items", []):
            t = it.get("track") or {}
            name = t.get("name")
            artists = [a.get("name") for a in (t.get("artists") or []) if a.get("name")]
            if name and artists:
                tracks.append({"artist": artists[0], "name": name})

        if data.get("next"):
            offset += limit
        else:
            break

    # Deduplicar por texto manteniendo orden
    seen = set()
    unique = []
    for tr in tracks:
        key = f'{tr["artist"].lower()} - {tr["name"].lower()}'
        if key not in seen:
            seen.add(key)
            unique.append(tr)

    return unique


def youtube_client():
    """Crea cliente de YouTube con OAuth + refresh token."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    return build("youtube", "v3", credentials=creds)


def youtube_playlist_video_ids(youtube, playlist_id: str):
    """Devuelve set de videoIds que ya están en la playlist."""
    ids = []
    page_token = None

    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token
        ).execute()

        for item in resp.get("items", []):
            vid = (item.get("snippet", {})
                   .get("resourceId", {})
                   .get("videoId"))
            if vid:
                ids.append(vid)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return set(ids)


def youtube_search_video_id(youtube, query: str):
    """Busca en YouTube 1 video para un query y devuelve videoId."""
    resp = youtube.search().list(
        part="snippet",
        q=query,
        maxResults=1,
        type="video",
        safeSearch="none"
    ).execute()

    items = resp.get("items", [])
    if not items:
        return None
    return items[0]["id"]["videoId"]


def youtube_add_to_playlist(youtube, playlist_id: str, video_id: str):
    """Agrega un video a una playlist."""
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id
            }
        }
    }
    return youtube.playlistItems().insert(part="snippet", body=body).execute()


def main():
    spotify_playlist_id = os.environ["SPOTIFY_PLAYLIST_ID"]
    youtube_playlist_id = os.environ["YOUTUBE_PLAYLIST_ID"]

    yt = youtube_client()
    existing = youtube_playlist_video_ids(yt, youtube_playlist_id)

    tracks = spotify_playlist_tracks(spotify_playlist_id)

    added = 0
    for tr in tracks:
        q = f'{tr["artist"]} - {tr["name"]}'
        vid = youtube_search_video_id(yt, q)

        if not vid:
            print(f"NO MATCH: {q}")
            continue

        if vid in existing:
            continue

        youtube_add_to_playlist(yt, youtube_playlist_id, vid)
        existing.add(vid)
        added += 1
        print(f"ADDED: {q} -> {vid}")

        time.sleep(0.2)  # mini pausa

    print(f"\nDONE. Added {added} new items.")


if __name__ == "__main__":
    main()
