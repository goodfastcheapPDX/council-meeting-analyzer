# app.py
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
import json
import re

app = Flask(__name__)

@app.route('/')
def home():
    return 'Hello, World!'


def get_authenticated_service():
    """Get an authenticated YouTube service using service account credentials"""
    SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
    
    # Load service account credentials from environment variable or file
    if 'GOOGLE_APPLICATION_CREDENTIALS_JSON' in os.environ:
        creds_json = os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON']
        credentials_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    else:
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
        credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    
    return build('youtube', 'v3', credentials=credentials)

def get_video_details(youtube, video_id):
    """Get basic video details like title and duration"""
    response = youtube.videos().list(
        part='snippet,contentDetails',
        id=video_id
    ).execute()
    
    if not response['items']:
        return None
    
    video_info = response['items'][0]
    
    # Parse duration (in ISO 8601 format, like PT1H20M30S)
    duration_str = video_info['contentDetails']['duration']
    duration_seconds = 0
    
    # Extract hours, minutes, and seconds
    hours_match = re.search(r'(\d+)H', duration_str)
    minutes_match = re.search(r'(\d+)M', duration_str)
    seconds_match = re.search(r'(\d+)S', duration_str)
    
    if hours_match:
        duration_seconds += int(hours_match.group(1)) * 3600
    if minutes_match:
        duration_seconds += int(minutes_match.group(1)) * 60
    if seconds_match:
        duration_seconds += int(seconds_match.group(1))
    
    return {
        'title': video_info['snippet']['title'],
        'channel': video_info['snippet']['channelTitle'],
        'published_at': video_info['snippet']['publishedAt'],
        'duration_seconds': duration_seconds
    }

def get_transcript(youtube, video_id):
    """Get the transcript for a YouTube video"""
    try:
        # First, check if captions are available
        captions_response = youtube.captions().list(
            part='snippet',
            videoId=video_id
        ).execute()
        
        if not captions_response.get('items'):
            return {'error': 'No captions found for this video'}
        
        # Find English captions (preferably not auto-generated)
        caption_id = None
        caption_track = None
        
        # First look for manual English captions
        for item in captions_response['items']:
            track_language = item['snippet']['language']
            track_name = item['snippet'].get('name', '')
            is_auto = 'auto-generated' in track_name.lower() or item['snippet'].get('trackKind') == 'ASR'
            
            if track_language == 'en' and not is_auto:
                caption_id = item['id']
                caption_track = item
                break
        
        # If no manual English captions, try auto-generated ones
        if not caption_id:
            for item in captions_response['items']:
                if item['snippet']['language'] == 'en':
                    caption_id = item['id']
                    caption_track = item
                    break
        
        # If still no English captions, take the first available
        if not caption_id and captions_response['items']:
            caption_id = captions_response['items'][0]['id']
            caption_track = captions_response['items'][0]
        
        if not caption_id:
            return {'error': 'No suitable captions found'}
        
        # Download the caption track as transcript
        download_response = youtube.captions().download(
            id=caption_id,
            tfmt='srt'  # SubRip format with timestamps
        ).execute()
        
        # Parse the SRT format
        transcript_text = download_response.decode('utf-8')
        
        # Process the SRT to extract text and timestamps
        segments = []
        full_text = ""
        
        # Basic SRT parser
        current_timestamp = ""
        current_text = []
        
        for line in transcript_text.split('\n'):
            line = line.strip()
            
            # Skip empty lines and numeric indices
            if not line or line.isdigit():
                continue
            
            # Handle timestamp lines (00:00:00,000 --> 00:00:05,000)
            if '-->' in line:
                # If we already have text, save the previous segment
                if current_text and current_timestamp:
                    text = ' '.join(current_text)
                    start_time, end_time = parse_srt_timestamp(current_timestamp)
                    
                    segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': text
                    })
                    
                    full_text += text + " "
                    current_text = []
                
                current_timestamp = line
            else:
                # This is transcript text
                current_text.append(line)
        
        # Add the last segment if there's any
        if current_text and current_timestamp:
            text = ' '.join(current_text)
            start_time, end_time = parse_srt_timestamp(current_timestamp)
            
            segments.append({
                'start': start_time,
                'end': end_time,
                'text': text
            })
            
            full_text += text
        
        # Format segments for output
        formatted_segments = []
        for segment in segments:
            start_str = format_time(segment['start'])
            end_str = format_time(segment['end'])
            formatted_segments.append(f"[{start_str} - {end_str}] {segment['text']}")
        
        # Get video details
        video_details = get_video_details(youtube, video_id)
        
        return {
            'success': True,
            'video': {
                'id': video_id,
                'title': video_details['title'],
                'channel': video_details['channel'],
                'duration': video_details['duration_seconds'],
                'url': f'https://www.youtube.com/watch?v={video_id}'
            },
            'transcript': {
                'full': full_text.strip(),
                'formatted': '\n\n'.join(formatted_segments),
                'segments': segments,
                'source': 'youtube_captions',
                'language': caption_track['snippet']['language']
            }
        }
        
    except Exception as e:
        return {'error': f'Error retrieving transcript: {str(e)}'}

def parse_srt_timestamp(timestamp_line):
    """Parse SRT timestamp format (00:00:00,000 --> 00:00:05,000)"""
    parts = timestamp_line.split(' --> ')
    start_str = parts[0].replace(',', '.')  # Convert comma to dot for decimal seconds
    end_str = parts[1].replace(',', '.')
    
    def parse_time(time_str):
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    
    return parse_time(start_str), parse_time(end_str)

def format_time(seconds):
    """Format seconds as HH:MM:SS"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"

@app.route('/api/transcript', methods=['GET'])
def transcript_api():
    """API endpoint to get transcript for a YouTube video"""
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'Missing video ID parameter. Use ?id=VIDEO_ID'}), 400
    
    # Initialize the YouTube API client
    try:
        youtube = get_authenticated_service()
    except Exception as e:
        return jsonify({'error': f'Authentication error: {str(e)}'}), 500
    
    # Get the transcript
    result = get_transcript(youtube, video_id)
    
    if 'error' in result:
        return jsonify(result), 500
    
    return jsonify(result)

@app.route('/api/create-doc', methods=['POST'])
def create_doc_api():
    """Create a Google Doc with the transcript and LLM analysis"""
    # This would be implemented to connect to Google Docs API
    # For now, return a placeholder response
    return jsonify({'message': 'Google Docs integration to be implemented'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
