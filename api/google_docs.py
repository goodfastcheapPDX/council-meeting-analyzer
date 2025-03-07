# google_docs.py
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import os

def get_docs_service():
    """Get an authenticated Google Docs service using service account credentials"""
    SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
    
    # Load service account credentials from environment variable or file
    if 'GOOGLE_APPLICATION_CREDENTIALS_JSON' in os.environ:
        creds_json = os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON']
        credentials_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    else:
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
        credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    
    # Return both Docs and Drive services
    docs_service = build('docs', 'v1', credentials=credentials)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    return docs_service, drive_service

def create_doc_with_transcript(transcript_data, analysis_text=None, folder_id=None):
    """Create a Google Doc with the transcript and analysis
    
    Args:
        transcript_data: The transcript data from the YouTube API
        analysis_text: Optional LLM analysis of the transcript
        folder_id: Optional Google Drive folder ID to place the document in
    
    Returns:
        dict: The document details including ID and URL
    """
    try:
        # Get authenticated services
        docs_service, drive_service = get_docs_service()
        
        # Extract data
        video_info = transcript_data['video']
        transcript = transcript_data['transcript']
        
        # Create a new document
        doc_title = f"Meeting Transcript: {video_info['title']} - {video_info['channel']}"
        document = {
            'title': doc_title
        }
        
        doc = docs_service.documents().create(body=document).execute()
        document_id = doc.get('documentId')
        
        # Move to specified folder if provided
        if folder_id:
            file_id = document_id
            
            # Get the file from Drive
            file = drive_service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents', []))
            
            # Move the file to the new folder
            drive_service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
        
        # Prepare document content
        requests = []
        
        # Add header with video information
        requests.append({
            'insertText': {
                'location': {
                    'index': 1
                },
                'text': f"# Meeting Transcript: {video_info['title']}\n\n"
            }
        })
        
        # Add video metadata
        current_index = len(f"# Meeting Transcript: {video_info['title']}\n\n")
        metadata_text = (
            f"Video URL: {video_info['url']}\n"
            f"Channel: {video_info['channel']}\n"
            f"Duration: {format_duration(video_info['duration'])}\n\n"
            f"---\n\n"
        )
        
        requests.append({
            'insertText': {
                'location': {
                    'index': current_index
                },
                'text': metadata_text
            }
        })
        
        current_index += len(metadata_text)
        
        # Add LLM analysis if provided
        if analysis_text:
            analysis_header = "## Analysis\n\n"
            requests.append({
                'insertText': {
                    'location': {
                        'index': current_index
                    },
                    'text': analysis_header
                }
            })
            
            current_index += len(analysis_header)
            
            requests.append({
                'insertText': {
                    'location': {
                        'index': current_index
                    },
                    'text': analysis_text + "\n\n---\n\n"
                }
            })
            
            current_index += len(analysis_text) + 6  # +6 for "\n\n---\n\n"
        
        # Add transcript header
        transcript_header = "## Full Transcript\n\n"
        requests.append({
            'insertText': {
                'location': {
                    'index': current_index
                },
                'text': transcript_header
            }
        })
        
        current_index += len(transcript_header)
        
        # Add formatted transcript
        requests.append({
            'insertText': {
                'location': {
                    'index': current_index
                },
                'text': transcript['formatted']
            }
        })
        
        # Apply styling
        # Make title heading 1
        requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': 1,
                    'endIndex': 1 + len(f"# Meeting Transcript: {video_info['title']}")
                },
                'paragraphStyle': {
                    'namedStyleType': 'HEADING_1',
                },
                'fields': 'namedStyleType'
            }
        })
        
        # Execute the requests
        docs_service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        
        # Generate shareable link
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        
        drive_service.permissions().create(
            fileId=document_id,
            body=permission
        ).execute()
        
        return {
            'success': True,
            'document_id': document_id,
            'document_url': f'https://docs.google.com/document/d/{document_id}/edit',
            'view_url': f'https://docs.google.com/document/d/{document_id}/view'
        }
        
    except Exception as e:
        return {'error': f'Error creating document: {str(e)}'}

def format_duration(seconds):
    """Format duration in seconds to a readable format"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"

def update_doc_with_analysis(document_id, analysis_text):
    """Update an existing Google Doc with analysis text"""
    try:
        # Get authenticated services
        docs_service, _ = get_docs_service()
        
        # First, get the document to find where to insert
        document = docs_service.documents().get(documentId=document_id).execute()
        
        # Find the position to insert (after metadata, before transcript)
        content = document.get('body').get('content')
        insert_index = None
        
        for item in content:
            if 'paragraph' in item:
                paragraph = item.get('paragraph')
                if paragraph.get('paragraphStyle', {}).get('namedStyleType') == 'HEADING_2':
                    # Found a heading, check if it's "Full Transcript"
                    text = ''.join([element.get('textRun', {}).get('content', '') 
                                  for element in paragraph.get('elements', [])])
                    if "Full Transcript" in text:
                        insert_index = item.get('startIndex')
                        break
        
        if not insert_index:
            # If we can't find "Full Transcript", insert at the beginning
            insert_index = 1
        
        # Prepare the analysis text
        analysis_header = "## Analysis\n\n"
        analysis_content = analysis_text + "\n\n---\n\n"
        
        # Create requests to update the document
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': insert_index
                    },
                    'text': analysis_header + analysis_content
                }
            },
            {
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': insert_index,
                        'endIndex': insert_index + len(analysis_header.rstrip())
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'HEADING_2',
                    },
                    'fields': 'namedStyleType'
                }
            }
        ]
        
        # Execute the requests
        docs_service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        
        return {
            'success': True,
            'document_id': document_id,
            'document_url': f'https://docs.google.com/document/d/{document_id}/edit'
        }
        
    except Exception as e:
        return {'error': f'Error updating document: {str(e)}'}
