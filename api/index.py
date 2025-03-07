# app.py
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
import json
import re

app = Flask(__name__)

def get_authenticated_service():
    """Get an authenticated YouTube service using service account credentials"""
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    
    print("Initializing YouTube authentication...")
    if 'GOOGLE_PRIVATE_KEY' in os.environ:
        creds_json = {
            "type": "service_account",
            "project_id": "flash-hour-453023-a0",
            "private_key_id": "d3e911dd9e09690aeacfc4b384212f2c79e5ccec",
            "private_key":  os.environ.get("GOOGLE_PRIVATE_KEY"),
            "client_email": "council-meeting-service@flash-hour-453023-a0.iam.gserviceaccount.com",
            "client_id": "106736129592262048868",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/council-meeting-service%40flash-hour-453023-a0.iam.gserviceaccount.com",
            "universe_domain": "googleapis.com"
        }


        print(creds_json)
        credentials_info = creds_json
        print("Found credentials in environment variable")
        
        credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        print("Successfully credentialed...")
        print(credentials)
    else:
        print("Credentials not found in environment variable, checking file...")
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
        credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    
    print("YouTube authentication successful")
    return build('youtube', 'v3', credentials=credentials)

def get_video_details(youtube, video_id):
    """Get basic video details like title and duration"""
    print(f"Fetching details for video: {video_id}")
    response = youtube.videos().list(
        part='snippet,contentDetails',
        id=video_id
    ).execute()
    
    if not response['items']:
        print("No video details found")
        return None
    
    video_info = response['items'][0]
    duration_str = video_info['contentDetails']['duration']
    print(f"Video duration (raw): {duration_str}")
    
    duration_seconds = 0
    hours_match = re.search(r'(\d+)H', duration_str)
    minutes_match = re.search(r'(\d+)M', duration_str)
    seconds_match = re.search(r'(\d+)S', duration_str)
    
    if hours_match:
        duration_seconds += int(hours_match.group(1)) * 3600
    if minutes_match:
        duration_seconds += int(minutes_match.group(1)) * 60
    if seconds_match:
        duration_seconds += int(seconds_match.group(1))
    
    print(f"Parsed duration: {duration_seconds} seconds")
    return {
        'title': video_info['snippet']['title'],
        'channel': video_info['snippet']['channelTitle'],
        'published_at': video_info['snippet']['publishedAt'],
        'duration_seconds': duration_seconds
    }

def get_transcript(youtube, video_id):
    """Get the transcript for a YouTube video"""
    print(f"Fetching transcript for video: {video_id}")
    try:
        captions_response = youtube.captions().list(
            part='snippet',
            videoId=video_id
        ).execute()
        
        if not captions_response.get('items'):
            print("No captions found")
            return {'error': 'No captions found for this video'}
        
        caption_id = None
        for item in captions_response['items']:
            if item['snippet']['language'] == 'en':
                caption_id = item['id']
                break
        
        if not caption_id:
            print("No English captions available")
            return {'error': 'No suitable captions found'}
        
        print(f"Downloading captions with ID: {caption_id}")
        download_response = youtube.captions().download(
            id=caption_id,
            tfmt='srt'
        ).execute()
        
        transcript_text = download_response.decode('utf-8')
        print("Transcript fetched successfully")
        
        return {'transcript': transcript_text}
    except Exception as e:
        print(f"Error retrieving transcript: {e}")
        return {'error': f'Error retrieving transcript: {str(e)}'}

@app.route('/api/transcript', methods=['GET'])
def transcript_api():
    """API endpoint to get transcript for a YouTube video"""
    print("Received request for transcript")
    print(f"Request args: {request.args}")
    video_id = request.args.get('id')
    
    if not video_id:
        print("Missing video ID parameter")
        return jsonify({'error': 'Missing video ID parameter. Use ?id=VIDEO_ID'}), 400
    
    try:
        youtube = get_authenticated_service()
    except Exception as e:
        print(f"Authentication error: {e}")
        return jsonify({'error': f'Authentication error: {str(e)}'}), 500
    
    result = get_transcript(youtube, video_id)
    
    if 'error' in result:
        print(f"Error in transcript retrieval: {result['error']}")
        return jsonify(result), 500
    
    print("Transcript successfully retrieved")
    return jsonify(result)

if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
