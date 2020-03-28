import json
import requests
import extract
import os
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from flask import Flask, request, redirect, g, render_template, Response
from urllib.parse import quote


app = Flask(__name__)
    
# API Keys
client_id = "26b7856504274aaf8e73196314a11837"
client_secret = "090108ca091346288c6c27e0d0eec073"

# API URLs
auth_url = "https://accounts.spotify.com/authorize"
token_url = "https://accounts.spotify.com/api/token"
base_url = "https://api.spotify.com/v1"

# Redirect uri and authorization scopes
redirect_uri = "http://127.0.0.1:8080/welcome"
scope = "user-top-read user-read-recently-played playlist-read-collaborative playlist-read-private"

# Image folder configuration
CUR_DIR = os.getcwd()
IMG_DIR = os.path.join(CUR_DIR, "/templates/images/energy.jpg")
app.config['UPLOAD_FOLDER'] = "/static/"

# Query parameters for authorization
auth_query = {
    "response_type": "code",
    "redirect_uri": redirect_uri,
    "scope": scope,
    "show_dialog": "false",
    "client_id": client_id
}


# Returns a token needed to access the Spotify API
def generate_access_token():
    # Requests refresh and access tokens (POST)
    auth_token = request.args['code']
    code_payload = {
        "grant_type": "authorization_code",
        "code": str(auth_token),
        "redirect_uri": redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret,
    }
    post_request = requests.post(token_url, data=code_payload)

    # Tokens returned to application
    response_data = json.loads(post_request.text)
    access_token = response_data["access_token"]
    refresh_token = response_data["refresh_token"]
    token_type = response_data["token_type"]
    expires_in = response_data["expires_in"]

    # Store the access token in a file and return the token
    f = open("token.txt", "w")
    f.write(access_token)
    f.close()
    return access_token


# GET a user's top artists
def get_top_artist_data(auth_header, time_range, limit, tag):
    endpoint = "{}/me/top/artists?time_range={}&limit={}".format(base_url, time_range, limit) 
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    top_artist_data = extract.top_artists(data, tag)
    return top_artist_data


# GET a user's top tracks
def get_top_tracks_data(auth_header, time_range, limit, tag):
    endpoint = "{}/me/top/tracks?time_range={}&limit={}".format(base_url, time_range, limit) 
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    top_tracks_data = extract.top_tracks(data, tag)
    return top_tracks_data


# GET a user's top tracks grouped by their top artists
def get_top_tracks_by_artist(auth_header):
    top_tracks = get_top_tracks_data(auth_header, 'long_term', '50', 'name')
    top_artists = get_top_artist_data(auth_header, 'long_term', '10', 'name')
    result = extract.top_tracks_by_artist(top_tracks, top_artists)
    return result


# GET a user's recent listening history
def get_recent_tracks_data(auth_header, limit):
    endpoint = "{}/me/player/recently-played?type=track&limit={}".format(base_url, limit)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    recent_tracks_data = extract.recent_tracks(data)
    return recent_tracks_data


# GET an artist's related artists
def get_related_artists(auth_header, artist_id):
    if artist_id is None:
        return None
    endpoint = "{}/artists/{}/related-artists".format(base_url, artist_id)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    related_artists = extract.related_artists(data)
    return related_artists


# GET the artist that a user has been listening to a lot recently (if there is one)
def get_frequent_artist(auth_header, artist_id):
    if artist_id is None:
        return None
    endpoint = "{}/artists/{}".format(base_url, artist_id)
    response = requests.get(endpoint, headers=auth_header)
    artist_name = json.loads(response.text)['name']
    return artist_name


# GET the track ids from the user's recent listening history
def get_recent_tracks_ids(auth_header, limit):
    endpoint = "{}/me/player/recently-played?type=track&limit={}".format(base_url, limit)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    recent_track_ids = extract.recent_track_ids(data)
    print(len(recent_track_ids))
    result = ','.join(recent_track_ids)
    return result


# GET the artwork of tracks
def get_track_images(auth_header, track_ids):
    endpoint = "{}/tracks?ids={}".format(base_url, track_ids)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    track_images = extract.track_images(data)
    return track_images


# GET audio features for several tracks and store necessary datapoints
def do_audio_analysis(auth_header, track_ids):
    endpoint = "{}/audio-features?ids={}".format(base_url, track_ids)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    datapoints = extract.get_audio_datapoints(data)
    return datapoints


# Graph data using matplotlib and seaborne
def make_graph(datapoints, tag):
    df = pd.DataFrame()
    df['Song Number'] = range(1, len(datapoints[tag]) + 1)
    y_title = tag.capitalize()
    df[y_title] = datapoints[tag]
    sns_plot = sns.barplot(x="Song Number", y=y_title, data=df)
    fig = sns_plot.get_figure()
    fig.set_size_inches(15, 7.5)     # Should change this to relative size of the screen
    fig.savefig('static/{t}.png'.format(t=tag))


# Returns a pandas dataframe containing data from the audio analysis
def get_dataframe(auth_header, data, label):
    df = pd.DataFrame()
    items = data['items'] 
    string_ids = ""
    for track in items:
        track_id = track['track']['id']
        string_ids += track_id
        string_ids += ','
    string_ids = string_ids[:-1]
    datapoints = do_audio_analysis(auth_header, string_ids)
    df['Danceability'] = datapoints['danceability']
    df['Tempo'] = datapoints['tempo']
    df['Instrumentalness'] = datapoints['instrumentalness']
    df['Energy'] = datapoints['energy']
    df['Label'] = [label] * (len(df.index))
    return df


# GET the tracks from a playlist
def get_tracks_from_playlist(auth_header, list_id, person_type):
    endpoint = "{}/playlists/{}/tracks".format(base_url, list_id)
    response = requests.get(endpoint, headers=auth_header)
    data = json.loads(response.text)
    datapoints = get_dataframe(auth_header, data, person_type)
    return datapoints


# Initial route for user authentication with Spotify
@app.route("/")
def index():
    # Redirects the user to the Spotify login page (first thing that happens upon app launch)
    url_args = "&".join(["{}={}".format(key, quote(val)) for key, val in auth_query.items()])
    authorization = "{}/?{}".format(auth_url, url_args)
    return redirect(authorization)


# Homepage of application
@app.route("/welcome")
def display_top_data():
    # Obtain an access token either by generating a new one or retrieving from storage
    f = open("token.txt", "r")
    if os.stat("token.txt").st_size == 0:
        access_token = generate_access_token()
    else:
        access_token = f.readline()

    # Use the token to get the necessary authorization header and access data
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    top_artist_data = get_top_artist_data(auth_header, 'long_term', '10', 'name')
    top_tracks_data = get_top_tracks_data(auth_header, 'long_term', '10', 'name')
    recent_tracks_data = get_recent_tracks_data(auth_header, '30')
    recent_track_ids = get_recent_tracks_ids(auth_header, '30')
    track_images = get_track_images(auth_header, recent_track_ids)


    # Render the HTML template accordingly based on wheter or not a "frequent artist" can be identified
    if recent_tracks_data[1] is None:
        return render_template("in.html", artists=top_artist_data, tracks=top_tracks_data,
                                recent=recent_tracks_data[0], related=0)
    else:
        related_artists = get_related_artists(auth_header, recent_tracks_data[1])
        frequent_artist = get_frequent_artist(auth_header, recent_tracks_data[1])
        return render_template("in.html", artists=top_artist_data, tracks=top_tracks_data,
                                recent=recent_tracks_data[0], related=related_artists, 
                                frequent=frequent_artist, images=track_images)

# Page for viewing top tracks
@app.route("/top-tracks")
def display_top_tracks():
    # Obtain the access token from where it is stored
    f = open("token.txt", "r")
    access_token = f.readline()
    
    # Use the token to get the necessary authorization header and access data
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    return render_template("tr.html")


# Page for viewing top tracks grouped by artist
@app.route("/top-tracks-by-artist")
def display_top_tracks_by_artist():
    # Obtain the access token from where it is stored
    f = open("token.txt", "r")
    access_token = f.readline()
    
    # Use the token to get the necessary authorization header and access data
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    top_tracks_by_artist_data = get_top_tracks_by_artist(auth_header)

    # Render HTML with the desired data
    return render_template("tracks.html", content=top_tracks_by_artist_data)


# Page for viewing an audio analysis graphS
@app.route("/audio-analysis", methods=['GET'])
def audio_analysis():
    # Obtain the access token from where it is stored
    f = open("token.txt", "r")
    access_token = f.readline()
    
    # Use the token to get the necessary authorization header and access data
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    track_ids = get_recent_tracks_ids(auth_header, '50')
    
    # Create a graph using datapoints
    datapoints = do_audio_analysis(auth_header, track_ids)
    matplotlib.use('Agg')
    matplotlib.style.use('ggplot')
    sns.set_style('dark')
    for key in datapoints:
        make_graph(datapoints, key)

    # Render HTML with the desired data
    img_1_file = os.path.join(app.config['UPLOAD_FOLDER'], 'danceability.png')
    img_2_file = os.path.join(app.config['UPLOAD_FOLDER'], 'energy.png')
    img_3_file = os.path.join(app.config['UPLOAD_FOLDER'], 'instrumentalness.png')
    img_4_file = os.path.join(app.config['UPLOAD_FOLDER'], 'tempo.png')
    return render_template("audio.html", img_1 = img_1_file, img_2 = img_2_file, img_3 = img_3_file, img_4 = img_4_file)


# Page for viewing a user's sentiment analysis
@app.route("/predict-personality")
def predict_personality():
    f = open("token.txt", "r")
    access_token = f.readline()
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    frame_list = []
    """
    Openness to experience (inventive/curious vs. consistent/cautious) = 1
    Conscientiousness (efficient/organized vs. easy-going/careless) = 2
    Extraversion (outgoing/energetic vs. solitary/reserved) = 3
    Agreeableness (friendly/compassionate vs. challenging/detached) = 4
    Neuroticism (sensitive/nervous vs. secure/confident) = 5
    """
    frame_list.append(get_tracks_from_playlist(auth_header,"0VHCKkJwUDBRry4JWOcDwF",5))#sensitive
    frame_list.append(get_tracks_from_playlist(auth_header,"0gY3yNHzIQ2zyIi8l4faO6",4))#compassion
    frame_list.append(get_tracks_from_playlist(auth_header,"0B0XVWCgz51yb8G0DPu7RO",3))#outgoing
    result = pd.concat(frame_list)
    result.to_csv(r'D:\Programming\spotify-data-app\tracks.csv', index = True)

    return render_template("person.html")


# Logs the user out of the application
@app.route("/logout")
def logout():
    return redirect("https://www.spotify.com/logout/")


# Run the server
if __name__ == "__main__":
    app.run(debug=True, port=8080)
