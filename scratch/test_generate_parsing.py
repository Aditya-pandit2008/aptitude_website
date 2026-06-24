import sys, os
# Add project root to sys.path
project_root = r'C:\\Users\\Aditya\\OneDrive\\Documents\\Desktop\\backend'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services import ai_service
from flask import Flask

# Mock _chat to return a malformed JSON without closing brace

def mock_chat(messages, **kwargs):
    # Simulate Groq returning JSON with missing closing brace and extra text
    return '{"title": "Sample Problem", "text": "Do something", "template_code": "def foo():\n    pass", "sample_test_cases": [{"input": "1", "expected_output": "1"}], "test_cases": [{"input": "2", "expected_output": "2"}]'  # missing closing }

ai_service._chat = mock_chat

app = Flask(__name__)
app.config['GROQ_API_KEY'] = 'dummy'
with app.app_context():
    result = ai_service.generate_coding_challenge('Algorithms', 'easy')
    print('Result:', result)
