from flask import Flask, render_template, request, jsonify, redirect, url_for
import google.generativeai as genai
import os
from pathlib import Path
import tempfile
import time
import base64
import json
import re
import traceback

app = Flask(__name__)

# Store conversation history and collected form data per session
conversation_sessions = {}
form_data_sessions = {}

@app.route('/')
def index():
    return redirect(url_for('assistant'))

@app.route('/assistant')
def assistant():
    return render_template('assistant.html')

@app.route('/form')
def form():
    return render_template('form.html')

@app.route('/transcribe', methods=['POST'])
def transcribe():
    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        
        # Configure Gemini with hardcoded API key
        genai.configure(api_key='AIzaSyAOp43RYJBqUwlioiZan0aGf9NCQFAbemY')
        
        # Read audio data directly
        audio_data = audio_file.read()
        
        try:
            # Create model for audio transcription
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            
            # Send audio data directly as base64
            response = model.generate_content([
                {
                    'mime_type': 'audio/webm',
                    'data': base64.b64encode(audio_data).decode('utf-8')
                },
                "Please transcribe this audio accurately. Only provide the transcription text without any additional commentary."
            ])
            
            transcription = response.text
            
            return jsonify({
                'success': True,
                'text': transcription
            })
            
        except Exception as e:
            raise e
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        session_id = data.get('session_id', 'default')
        
        # Configure Gemini
        genai.configure(api_key='AIzaSyAOp43RYJBqUwlioiZan0aGf9NCQFAbemY')
        
        # Initialize conversation history for new sessions
        if session_id not in conversation_sessions:
            conversation_sessions[session_id] = []
            form_data_sessions[session_id] = {}
        
        # System prompt for the Indian Bank Deposit Slip form-filling assistant
        system_prompt = """You are a helpful, patient assistant for filling out Indian Bank Deposit Slip forms, designed especially for elderly users who may not be tech-savvy.

**SMART BEHAVIORS:**

1. **Amount Processing:**
   - When user says an amount (e.g., "5000"), automatically convert it to words yourself (e.g., "Five Thousand Rupees")
   - DO NOT ask them to repeat the amount in words
   - Just confirm: "Got it, ₹5,000 (Five Thousand Rupees)"

2. **Denomination Intelligence:**
   - If user mentions denominations (e.g., "2 notes of 2000"), calculate automatically:
     * 2 × ₹2000 = ₹4000
   - DO NOT ask about other denominations if they've already given you the total
   - If the denomination breakdown matches the total amount, skip asking about other notes
   - If it doesn't match, politely ask: "I calculated ₹4000 from the notes you mentioned, but you said the total is ₹5000. Do you have ₹1000 in other notes?"

3. **Email Handling:**
   - Email is OPTIONAL
   - When asking for email, say: "Do you have an email address? (It's optional - you can skip this if you don't have one, or ask a family member to help you later)"
   - If they say "no", "don't have", "skip", or seem confused, respond warmly: "No problem! We can skip the email. Let's continue..."
   - DO NOT insist on email

4. **Natural Number Understanding:**
   - Understand natural speech: "two thousand five hundred" = 2500
   - "twenty five lakhs" = 2500000
   - "one and half thousand" = 1500
   - Convert these automatically to digits

5. **Validation with Empathy:**
   - If account number is not 12 digits, gently say: "I noticed the account number you provided has [X] digits. Indian Bank account numbers are usually 12 digits. Could you check once?"
   - For dates, accept formats like: "today", "29th October", "29/10/2025", "29-10-2025"
   - If they say "today", calculate today's date and confirm

6. **Helpful Guidance:**
   - If user seems confused about any term, explain it simply
   - Break down complex questions into simpler ones
   - Use examples when helpful

**Information to Collect:**

**Basic Information:**
1. Branch name
2. Date (accept "today" or any date format, normalize to DD/MM/YYYY)
3. Account number (12 digits - validate gently)
4. Account holder's full name
5. Telephone/Mobile number
6. Email ID (OPTIONAL - skip if they don't have one)

**Deposit Details:**
7. Type of deposit - Cash or Cheque?
8. Total amount (convert numbers to words automatically)

**For CASH deposits:**
- If they mention denomination breakdown, calculate and verify it matches the total
- Only ask for missing denominations if totals don't match
- For deposits ≥₹50,000: Ask about Form 60/61 (explain: "This is a tax form - if you have it, great! If not, the bank will help you with it")

**For CHEQUE deposits:**
- Cheque number
- Cheque date  
- Bank and branch name on the cheque

**Communication Style:**
- Be warm, patient, and encouraging
- Use simple language
- Confirm each piece of information clearly
- Add conversational responses: "Great!", "Perfect!", "Thank you!"
- Ask ONE question at a time
- Never make them feel rushed or confused

After collecting all information, when user confirms, provide data in this format:
{FORM_DATA: {"branch_name": "value", "date": "DD/MM/YYYY", "account_number": "12digits", "account_holder_name": "name", "telephone_mobile_number": "phone", "email_id": "email or empty", "deposit_type": "Cash or Cheque", "total_amount": "amount", "amount_in_words": "words", "denom_2000_qty": "0", "denom_500_qty": "0", "denom_200_qty": "0", "denom_100_qty": "0", "denom_50_qty": "0", "denom_20_qty": "0", "denom_10_qty": "0", "denom_5_qty": "0", "denom_coins_qty": "0"}}

For cheque: add "cheque_number", "cheque_date", "cheque_bank"

Remember: Be helpful, patient, and make this easy for elderly users!"""

        # Add system prompt for first message
        if len(conversation_sessions[session_id]) == 0:
            conversation_sessions[session_id].append({
                'role': 'user',
                'parts': [system_prompt]
            })
            conversation_sessions[session_id].append({
                'role': 'model',
                'parts': ['Understood. I will help users fill Indian Bank Deposit Slip by asking questions one at a time and collecting the required information.']
            })
        
        # Add user message to history
        conversation_sessions[session_id].append({
            'role': 'user',
            'parts': [user_message]
        })
        
        # Create model and generate response
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        chat = model.start_chat(history=conversation_sessions[session_id][:-1])
        response = chat.send_message(user_message)
        
        # Add assistant response to history
        conversation_sessions[session_id].append({
            'role': 'model',
            'parts': [response.text]
        })
        
        # Extract form data if present
        response_text = response.text
        form_complete = False
        extracted_form_data = {}
        
        if '{FORM_DATA:' in response_text or 'FORM_DATA' in response_text:
            form_complete = True
            
            # Try to find JSON data
            match = re.search(r'\{FORM_DATA:\s*(\{.*?\})\}', response_text, re.DOTALL)
            if not match:
                match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not match:
                match = re.search(r'(\{[^{}]*"branch_name"[^{}]*\})', response_text, re.DOTALL)
            
            if match:
                try:
                    json_str = match.group(1)
                    extracted_data = json.loads(json_str)
                    
                    # Process denomination breakdown if present
                    if 'denomination_breakdown' in extracted_data:
                        denom = extracted_data['denomination_breakdown']
                        for key, value in denom.items():
                            if key == 'coins':
                                extracted_data['denom_coins_qty'] = str(value)
                            else:
                                extracted_data[f'denom_{key}_qty'] = str(value)
                        del extracted_data['denomination_breakdown']
                    
                    # Ensure all denomination fields exist
                    for denom in ['2000', '500', '200', '100', '50', '20', '10', '5', 'coins']:
                        if f'denom_{denom}_qty' not in extracted_data:
                            extracted_data[f'denom_{denom}_qty'] = '0'
                    
                    form_data_sessions[session_id].update(extracted_data)
                    extracted_form_data = extracted_data
                    print(f"Extracted form data: {extracted_form_data}")
                except Exception as e:
                    print(f"Error parsing form data: {e}")
                    form_complete = False
        
        # Clean response text
        clean_response = response_text
        if '{FORM_DATA:' in clean_response:
            clean_response = re.sub(r'\{FORM_DATA:.*?\}', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'```json.*?```', '', clean_response, flags=re.DOTALL)
        clean_response = clean_response.strip()
        
        return jsonify({
            'success': True,
            'response': clean_response,
            'session_id': session_id,
            'form_complete': form_complete,
            'form_data': extracted_form_data if form_complete else {}
        })
        
    except Exception as e:
        print(f"Error in chat: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/get_form_data', methods=['POST'])
def get_form_data():
    try:
        data = request.get_json()
        session_id = data.get('session_id', 'default')
        
        if session_id in form_data_sessions:
            return jsonify({
                'success': True,
                'form_data': form_data_sessions[session_id]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No form data found for this session'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/reset_conversation', methods=['POST'])
def reset_conversation():
    try:
        data = request.get_json()
        session_id = data.get('session_id', 'default')
        
        if session_id in conversation_sessions:
            del conversation_sessions[session_id]
        if session_id in form_data_sessions:
            del form_data_sessions[session_id]
        
        return jsonify({
            'success': True,
            'message': 'Conversation and form data reset successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
