# app_integration.py
from flask import Flask, request, jsonify
import requests
import os
import json
from google_docs import create_doc_with_transcript, update_doc_with_analysis

app = Flask(__name__)

def call_openai_api(transcript):
    """Call OpenAI API to analyze the transcript"""
    try:
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            return {'error': 'OpenAI API key not found in environment variables'}
        
        # Prepare the system message with instructions for formatting
        system_message = """
        You are an expert municipal analyst tasked with analyzing city council meeting transcripts.
        Your analysis should be comprehensive yet concise, factual, and politically neutral.
        
        Format your analysis with the following sections:
        
        ## EXECUTIVE SUMMARY
        A concise (150-250 word) overview of the entire meeting highlighting key decisions and outcomes.
        
        ## AGENDA ITEMS
        For each agenda item discussed:
        - Item title/number
        - Brief summary (75-100 words)
        - Key points of discussion
        - Outcome (approved, denied, tabled, etc.)
        
        ## VOTING RECORD
        Table format listing all votes taken:
        - Motion description
        - Moved by
        - Seconded by
        - Outcome (passed/failed)
        - Vote count
        - Dissenting votes
        
        ## ACTION ITEMS
        List all action items mentioned:
        - Description
        - Person responsible
        - Deadline (if mentioned)
        - Priority level
        
        ## PUBLIC PARTICIPATION
        For each public commenter:
        - Name (if stated)
        - Topic addressed
        - Position summary
        - Council response
        
        ## KEY RELATIONSHIPS & DYNAMICS
        Analysis of interactions:
        - Noteworthy agreements/disagreements
        - Coalition patterns
        - Significant exchanges
        """
        
        # Prepare the user message with the transcript
        user_message = f"Please analyze this city council meeting transcript:\n\n{transcript}"
        
        # Call the OpenAI API
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {openai_api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-4', # Use GPT-4 for better analysis
                'messages': [
                    {'role': 'system', 'content': system_message},
                    {'role': 'user', 'content': user_message}
                ],
                'temperature': 0.2, # Lower temperature for more factual output
                'max_tokens': 4000  # Adjust based on expected analysis length
            }
        )
        
        if response.status_code != 200:
            return {'error': f'OpenAI API error: {response.text}'}
        
        result = response.json()
        analysis = result['choices'][0]['message']['content']
        
        return {'success': True, 'analysis': analysis}
        
    except Exception as e:
        return {'error': f'Error calling OpenAI API: {str(e)}'}

def call_claude_api(transcript):
    """Call Anthropic's Claude API to analyze the transcript"""
    try:
        claude_api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not claude_api_key:
            return {'error': 'Claude API key not found in environment variables'}
        
        # Prepare the system message with instructions for formatting
        system_prompt = """
        You are an expert municipal analyst tasked with analyzing city council meeting transcripts.
        Your analysis should be comprehensive yet concise, factual, and politically neutral.
        
        Format your analysis with the following sections:
        
        ## EXECUTIVE SUMMARY
        A concise (150-250 word) overview of the entire meeting highlighting key decisions and outcomes.
        
        ## AGENDA ITEMS
        For each agenda item discussed:
        - Item title/number
        - Brief summary (75-100 words)
        - Key points of discussion
        - Outcome (approved, denied, tabled, etc.)
        
        ## VOTING RECORD
        Table format listing all votes taken:
        - Motion description
        - Moved by
        - Seconded by
        - Outcome (passed/failed)
        - Vote count
        - Dissenting votes
        
        ## ACTION ITEMS
        List all action items mentioned:
        - Description
        - Person responsible
        - Deadline (if mentioned)
        - Priority level
        
        ## PUBLIC PARTICIPATION
        For each public commenter:
        - Name (if stated)
        - Topic addressed
        - Position summary
        - Council response
        
        ## KEY RELATIONSHIPS & DYNAMICS
        Analysis of interactions:
        - Noteworthy agreements/disagreements
        - Coalition patterns
        - Significant exchanges
        """
        
        # Prepare the user message with the transcript
        user_message = f"Please analyze this city council meeting transcript:\n\n{transcript}"
        
        # Call the Claude API
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': claude_api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'claude-3-opus-20240229', # Use Claude 3 Opus for better analysis
                'system': system_prompt,
                'messages': [
                    {'role': 'user', 'content': user_message}
                ],
                'temperature': 0.2, # Lower temperature for more factual output
                'max_tokens': 4000  # Adjust based on expected analysis length
            }
        )
        
        if response.status_code != 200:
            return {'error': f'Claude API error: {response.text}'}
        
        result = response.json()
        analysis = result['content'][0]['text']
        
        return {'success': True, 'analysis': analysis}
        
    except Exception as e:
        return {'error': f'Error calling Claude API: {str(e)}'}

@app.route('/api/analyze', methods=['POST'])
def analyze_transcript():
    """Analyze a transcript using an LLM"""
    try:
        data = request.json
        if not data or 'transcript' not in data:
            return jsonify({'error': 'Missing transcript in request body'}), 400
        
        transcript = data['transcript']
        
        # Choose which LLM to use based on configuration
        llm_choice = os.environ.get('LLM_CHOICE', 'openai').lower()
        
        if llm_choice == 'claude':
            result = call_claude_api(transcript)
        else:
            result = call_openai_api(transcript)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Error analyzing transcript: {str(e)}'}), 500

@app.route('/api/process-video', methods=['POST'])
def process_video():
    """Complete workflow to process a YouTube video:
    1. Get transcript
    2. Analyze with LLM
    3. Create Google Doc with both
    """
    try:
        data = request.json
        if not data or 'video_id' not in data:
            return jsonify({'error': 'Missing video_id in request body'}), 400
        
        video_id = data['video_id']
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        # Step 1: Get the transcript
        transcript_api_url = f"{request.host_url.rstrip('/')}/api/transcript?id={video_id}"
        transcript_response = requests.get(transcript_api_url)
        
        if transcript_response.status_code != 200:
            return jsonify({'error': f'Failed to get transcript: {transcript_response.text}'}), 500
        
        transcript_data = transcript_response.json()
        
        # Step 2: Analyze the transcript
        analysis_result = None
        if data.get('analyze', True):  # Default to analyzing if not specified
            llm_choice = os.environ.get('LLM_CHOICE', 'openai').lower()
            
            if llm_choice == 'claude':
                analysis_result = call_claude_api(transcript_data['transcript']['full'])
            else:
                analysis_result = call_openai_api(transcript_data['transcript']['full'])
            
            if 'error' in analysis_result:
                return jsonify({'error': f'Analysis failed: {analysis_result["error"]}'}), 500
        
        # Step 3: Create Google Doc
        analysis_text = analysis_result['analysis'] if analysis_result else None
        doc_result = create_doc_with_transcript(transcript_data, analysis_text, folder_id)
        
        if 'error' in doc_result:
            return jsonify({'error': f'Document creation failed: {doc_result["error"]}'}), 500
        
        # Return success with document link
        return jsonify({
            'success': True,
            'video': transcript_data['video'],
            'document': {
                'id': doc_result['document_id'],
                'url': doc_result['document_url'],
                'view_url': doc_result['view_url']
            },
            'analysis_completed': analysis_result is not None
        })
        
    except Exception as e:
        return jsonify({'error': f'Error processing video: {str(e)}'}), 500

@app.route('/api/update-analysis', methods=['POST'])
def update_analysis():
    """Update an existing Google Doc with a new analysis"""
    try:
        data = request.json
        if not data or 'document_id' not in data or 'transcript' not in data:
            return jsonify({'error': 'Missing document_id or transcript in request body'}), 400
        
        document_id = data['document_id']
        transcript = data['transcript']
        
        # Analyze the transcript
        llm_choice = os.environ.get('LLM_CHOICE', 'openai').lower()
        
        if llm_choice == 'claude':
            analysis_result = call_claude_api(transcript)
        else:
            analysis_result = call_openai_api(transcript)
        
        if 'error' in analysis_result:
            return jsonify({'error': f'Analysis failed: {analysis_result["error"]}'}), 500
        
        # Update the Google Doc
        update_result = update_doc_with_analysis(document_id, analysis_result['analysis'])
        
        if 'error' in update_result:
            return jsonify({'error': f'Document update failed: {update_result["error"]}'}), 500
        
        # Return success with document link
        return jsonify({
            'success': True,
            'document': {
                'id': update_result['document_id'],
                'url': update_result['document_url']
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Error updating analysis: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
