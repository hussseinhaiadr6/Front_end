import os
import uuid
from flask import Flask, render_template, session, request, redirect, url_for, flash, jsonify
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
import msal
import requests
import json5
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from Utils import help_text, fetch_secret_from_keyvault
from Data_visulisation.Utilities.Utils import load_chart_configs


# Force override env variables, and explicitly point to your .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

KV_NAME = os.getenv("KV_NAME")
print(f" Kv name from .env is {KV_NAME}")
URL_PREFIX = '/ai/chatbot/ra' 
# static_url_path=f"{URL_PREFIX}/static"
# --- Configuration ---
app = Flask(__name__, static_url_path=f"{URL_PREFIX}/static")
# app = Flask(__name__)

# PUBLIC_HOST = os.getenv('PUBLIC_HOST', 'apmeawest-catalogue.bee.store') # Your App Gateway Host
PUBLIC_SCHEME = os.getenv('PUBLIC_SCHEME', 'https')


# app.config['SERVER_NAME'] = PUBLIC_HOST

app.config['APPLICATION_ROOT'] = URL_PREFIX
app.config['PREFERRED_URL_SCHEME'] = PUBLIC_SCHEME




app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1) # You can add x_for=1 if needed

# Flask-Session configuration
app.config['SECRET_KEY'] = fetch_secret_from_keyvault(os.getenv('FLASK_SECRET_KEY'), KV_NAME)
if app.config['SECRET_KEY'] == 'default-insecure-fallback-key-change-me':
    app.logger.warning(
        "WARNING: Using default SECRET_KEY. Please set FLASK_SECRET_KEY in your .env file!")

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './sessions'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

# Azure AD configuration
CLIENT_ID = fetch_secret_from_keyvault(os.getenv('AZURE_CLIENT_ID_secret'), KV_NAME)
print(f" APP id is : {CLIENT_ID}") # For local debugging, consider removing for production logs
CLIENT_SECRET = fetch_secret_from_keyvault(os.getenv('AZURE_CLIENT_SECRET_bot'), KV_NAME)
TENANT_ID = os.getenv('AZURE_TENANT_ID_bot')
AUTHORITY = os.getenv('AZURE_AUTHORITY_bot')
REDIRECT_PATH = os.getenv('REDIRECT_PATH', '/getAToken') # IMPORTANT: Set this in .env for your callback path e.g. /ai/chatbot/ra/oauth2callback
SCOPE = os.getenv('SCOPE', "User.Read").split()

# Target API configuration
API_URL = os.getenv('API_URL')
API_SUBSCRIPTION_KEY = fetch_secret_from_keyvault(os.getenv('API_SUBSCRIPTION_KEY'), KV_NAME)

# Check for essential configuration variables
if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, AUTHORITY, API_URL, API_SUBSCRIPTION_KEY]):
    # This will crash the app on startup if vars are missing, which is good for DX.
    raise ValueError(
        "One or more critical environment variables (Azure AD or API details) are missing. Check your .env file.")

# --- Initialization ---
Session(app)
CSRFProtect(app)

# --- MSAL Helper Functions ---
def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache
    )

def _load_cache():
    cache = msal.SerializableTokenCache()
    if "token_cache" in session:
        cache.deserialize(session["token_cache"])
    return cache

def _save_cache(cache):
    if cache.has_state_changed:
        session["token_cache"] = cache.serialize()

def _build_auth_url(scopes=None, state=None):
    # `url_for` will use `request.host`, `request.scheme` etc. which should now be corrected by ProxyFix
    redirect_uri = url_for("authorized", _external=True) #,_scheme='https' Explicit _scheme='https' as a fallback/override
    app.logger.info(f"Generating auth url with redirect_uri: {redirect_uri}. "
                    f"Current request context: host='{request.host}', scheme='{request.scheme}', "
                    f"url_root='{request.url_root}'")
    msal_app = _build_msal_app()
    return msal_app.get_authorization_request_url(
        scopes or SCOPE,
        state=state or str(uuid.uuid4()),
        redirect_uri=redirect_uri
    )

def _get_token_from_cache(scopes=None):
    cache = _load_cache()
    cca = _build_msal_app(cache=cache)
    accounts = cca.get_accounts()
    if accounts:
        result = cca.acquire_token_silent(scopes or SCOPE, account=accounts[0])
        _save_cache(cache)
        return result
    app.logger.info("No suitable token found in cache.")
    return None


@app.route(REDIRECT_PATH) # Path defined by REDIRECT_PATH env var
def authorized():
    # ... (state check, error check unchanged)
    state = request.args.get('state')
    if state != session.get("state"):
        app.logger.warning(f"State mismatch error during Azure AD callback. Expected: '{session.get('state')}', Got: '{state}'")
        flash("Login failed due to a state mismatch. Please try logging in again.", "error")
        session.pop("state", None)
        return redirect(url_for("login"))

    session.pop("state", None)

    if "error" in request.args:
        error_description = request.args.get('error_description', 'No description provided.')
        app.logger.error(f"Azure AD Login Error: {request.args['error']}. Description: {error_description}")
        flash(f"Login failed: {error_description}", "error")
        return redirect(url_for("login"))

    code = request.args.get('code')
    if code:
        cache = _load_cache()
        cca = _build_msal_app(cache=cache)
        try:
            token_redirect_uri = url_for("authorized", _external=True,) # _scheme='https' Explicit _scheme for safety
            app.logger.info(f"Attempting to acquire token by authorization code. Callback redirect_uri for token request: {token_redirect_uri}")

            result = cca.acquire_token_by_authorization_code(
                code,
                scopes=SCOPE,
                redirect_uri=token_redirect_uri
            )

            if "error" in result:
                error_description = result.get('error_description', 'Unknown token acquisition error.')
                app.logger.error(
                    f"Token Acquisition Error: {result.get('error')}. Description: {error_description}. Full result: {result}")
                flash(f"Could not acquire token: {error_description}", "error")
                return redirect(url_for("login"))

            id_token_claims = result.get('id_token_claims', {})
            user_info = {
                'name': id_token_claims.get('name', 'Unknown User'),
                'oid': id_token_claims.get('oid'),
                'preferred_username': id_token_claims.get('preferred_username')
            }
            session["user"] = user_info
            session["conversation"] = []
            session["thread_id"] = None
            _save_cache(cache)
            app.logger.info(
                f"User '{user_info.get('preferred_username')}' (oid: {user_info.get('oid')}) logged in successfully. Cleared session history.")
            flash(f"Welcome, {session['user']['name']}!", "success")
            return redirect(url_for("index"))

        except Exception as e:
            app.logger.error(f"Unexpected error during token acquisition: {e}", exc_info=True)
            flash(f"An unexpected error occurred during login: {str(e)}", "error")
            return redirect(url_for("login"))
    else:
        app.logger.warning("Azure AD callback received without code or error.")
        flash("Received an unexpected response from the identity provider.", "warning")
        return redirect(url_for("login"))

@app.route("/ai/chatbot/ra/logout")
def logout():
    # ... (rest of the function is unchanged)
    user_name = session.get("user", {}).get("name", "User")
    sid_to_delete = getattr(session, 'sid', None)

    app.logger.debug(f"Session ID to potentially delete: {sid_to_delete}")
    session.clear()
    app.logger.info(f"User '{user_name}' logged out. Session data cleared.")

    if sid_to_delete:
        session_file_path = os.path.join(app.config['SESSION_FILE_DIR'], sid_to_delete)
        try:
            if os.path.exists(session_file_path):
                os.remove(session_file_path)
                app.logger.info(f"Successfully deleted session file: {session_file_path}")
            else:
                app.logger.warning(
                    f"Session file not found for deletion: {session_file_path}")
        except OSError as e:
            app.logger.error(
                f"Error deleting session file {session_file_path}: {e}", exc_info=True)
        except Exception as e:
            app.logger.error(
                f"Unexpected error during session file deletion: {e}", exc_info=True)

    logout_redirect_uri = url_for("index", _external=True)#,_scheme='https'
    app.logger.info(
        f"Redirecting user to Azure AD logout with post_logout_redirect_uri: {logout_redirect_uri}")
    return redirect(
        AUTHORITY + "/oauth2/v2.0/logout" +
        "?post_logout_redirect_uri=" + logout_redirect_uri
    )

# --- Routes ---


@app.route("/ai/chatbot/ra/")
def index():
    # ... (rest of the function is unchanged)
    user_info = session.get("user")
    if not user_info:
        app.logger.info("User not authenticated, redirecting to custom login page.")
        return redirect(url_for("login"))

    if 'conversation' not in session:
        session['conversation'] = []
        app.logger.info(f"Initialized empty conversation history for user {user_info.get('oid')}")

    return render_template('index.html',
                           user=user_info,
                           conversation=session.get('conversation', []))

@app.route("/ai/chatbot/ra/login")
def login():
    # ... (rest of the function is unchanged)
    if session.get("user"):
        app.logger.info("User already logged in, redirecting to index from /login.")
        return redirect(url_for("index"))
    app.logger.info("Displaying custom login page.")
    return render_template("login.html")

@app.route("/ai/chatbot/ra/start_login")
def start_login():
    # ... (rest of the function is unchanged)
    if session.get("user"):
        app.logger.info("User already logged in, redirecting to index from /start_login.")
        return redirect(url_for("index"))

    session["state"] = str(uuid.uuid4())
    auth_url = _build_auth_url(state=session["state"]) # This will now use the corrected request context
    app.logger.info(
        f"Redirecting user to Azure AD for login via /start_login. Auth URL: {auth_url}, State: {session['state']}")
    return redirect(auth_url)


@app.route("/ai/chatbot/ra/generate_charts", methods=["POST"])
def generate_charts():
    user_info = session.get("user")
    if not user_info:
        app.logger.warning("Unauthorized AJAX attempt to generate charts.")
        return jsonify({"status": "error", "error_message": "Authentication required."}), 401

    if not request.is_json:
        app.logger.warning("/generate_charts: Invalid request format: Not JSON.")
        return jsonify({"status": "error", "error_message": "Invalid request format. Expected JSON."}), 400

    data = request.get_json()
    user_instruction = data.get("user_instruction")
    user_data = data.get("user_data")

    if not user_instruction or not user_instruction.strip():
        app.logger.warning("/generate_charts: Missing or empty user_instruction.")
        return jsonify({"status": "error", "error_message": "Missing user instruction for chart generation."}), 400
    if not user_data or not user_data.strip():
        app.logger.warning("/generate_charts: Missing or empty user_data (bot response).")
        return jsonify({"status": "error", "error_message": "Missing bot response data required for chart generation."}), 400

    app.logger.info(f"Generating charts for user '{user_info.get('preferred_username')}' (oid: {user_info.get('oid')}).")
    chart_configs = []

    try:
        CHART_API_URL= "https://beeapimprod.azure-api.net/ai/ra/chatbot/generate_charts"
        # Call the FastAPI endpoint instead of local function
        headers = {
            'Content-Type': 'application/json',
            'Ocp-Apim-Subscription-Key': API_SUBSCRIPTION_KEY
        }
        payload = {
            "user_data": user_data.strip(),
            "user_instruction": user_instruction.strip()
        }
        
        app.logger.info(f"Sending chart generation request to API ({CHART_API_URL})")
        response = requests.post(CHART_API_URL, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        api_response_data = response.json()
        app.logger.debug(f"Chart API Raw Response: {api_response_data}")
        
        raw_configs_string = api_response_data.get('chart_configs')
        
        if not raw_configs_string:
            app.logger.warning("API call successful but 'chart_configs' field was missing or empty.")
            return render_template('charts_template.html',
                                 page_title='Chart Generation Error',
                                 chart_configs=[],
                                 error_message="No chart configurations were generated."), 200
        
        # Keep the original post-processing logic
        if raw_configs_string == " Error: Could not genrate chart":
             app.logger.error(f"/generate_charts: Chart generation function returned a specific error message.")
             return render_template('charts_template.html',
                                    page_title='Chart Generation Error',
                                    chart_configs=[],
                                    error_message="Failed to generate valid chart configurations from the provided data. Please try refining your request."), 500

        chart_configs = load_chart_configs(raw_configs_string)
        if not isinstance(chart_configs, list) or not chart_configs:
             app.logger.warning("/generate_charts: Parsed configs are not a list or list is empty.")
             return render_template('charts_template.html',
                                    page_title='Generated Charts',
                                    chart_configs=[]), 200

        app.logger.info(f"/generate_charts: Successfully generated {len(chart_configs)} chart configurations. Rendering template.")
        return render_template('charts_template.html',
                               page_title='Generated Charts',
                               chart_configs=chart_configs)
                               
    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code
        error_message = f"API Error: Status Code {status_code}."
        try:
            error_details = http_err.response.json().get('error', http_err.response.text[:200])
            error_message += f" Details: {error_details}"
        except:
            pass
        app.logger.error(f"HTTP error calling Chart API: {http_err}", exc_info=True)
        return render_template('charts_template.html',
                             page_title='Chart Generation Error',
                             chart_configs=[],
                             error_message=error_message), status_code
                             
    except ValueError as ve:
        app.logger.error(f"/generate_charts: Error during chart configuration generation (ValueError): {ve}", exc_info=True)
        return render_template('charts_template.html', page_title='Chart Generation Error', chart_configs=[], error_message=f"Failed to generate chart configurations: {str(ve)}"), 500
    except json5.Json5Error as je:
         app.logger.error(f"/generate_charts: Error parsing generated chart configs (Json5Error): {je}", exc_info=True)
         return render_template('charts_template.html', page_title='Chart Generation Error', chart_configs=[], error_message=f"Failed to parse chart configurations: {str(je)}"), 500
    except Exception as e:
        app.logger.error(f"/generate_charts: An unexpected error occurred during chart generation: {e}", exc_info=True)
        return render_template('charts_template.html', page_title='Chart Generation Error', chart_configs=[], error_message=f"An unexpected error occurred during chart generation: {str(e)}"), 500

@app.route("/ai/chatbot/ra/generate_html_table", methods=["POST"])
def generate_html_table():
    user_info = session.get("user")
    if not user_info:
        app.logger.warning("Unauthorized AJAX attempt to generate table.")
        return jsonify({"status": "error", "error_message": "Authentication required."}), 401

    if not request.is_json:
        app.logger.warning("/generate_html_table: Invalid request format: Not JSON.")
        return jsonify({"status": "error", "error_message": "Invalid request format. Expected JSON."}), 400

    data = request.get_json()
    user_instruction = data.get("user_instruction")
    user_data = data.get("user_data")
    print(f"the user data is: {user_data} and the user instruction is: {user_instruction}")

    if not user_instruction or not user_instruction.strip():
        app.logger.warning("/generate_html_table: Missing or empty user_instruction.")
        return jsonify({"status": "error", "error_message": "Missing user instruction for table generation."}), 400
    if not user_data or not user_data.strip():
        app.logger.warning("/generate_html_table: Missing or empty user_data (bot response).")
        return jsonify({"status": "error", "error_message": "Missing bot response data required for table generation."}), 400

    app.logger.info(f"Generating HTML table for user '{user_info.get('preferred_username')}' (oid: {user_info.get('oid')}).")
    raw_table_html = ""

    try:
        TABLE_API_URL = "https://beeapimprod.azure-api.net/ai/ra/chatbot/generate_html_charts"
        # Call the FastAPI endpoint instead of local function
        headers = {
            'Content-Type': 'application/json',
            'Ocp-Apim-Subscription-Key': API_SUBSCRIPTION_KEY
        }
        payload = {
            "user_data": user_data.strip(),
            "user_instruction": user_instruction.strip()
        }
        
        app.logger.info(f"Sending table generation request to API ({TABLE_API_URL})")
        response = requests.post(TABLE_API_URL, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        api_response_data = response.json()
        
        raw_table_html = api_response_data.get('html_content', '')
        app.logger.debug(f"/generate_html_table: Raw LLM HTML response snippet: {raw_table_html[:500]}...")
        
        # Keep the original validation logic
        trimmed_html = raw_table_html.strip().lower() if raw_table_html else ""
        is_valid_table_html = trimmed_html.startswith("<table") and trimmed_html.endswith("</table>")

        if not is_valid_table_html:
            app.logger.warning("/generate_html_table: Generated string does not appear to be a valid HTML table.")
            return render_template('html_table_template.html',
                                   page_title='Table Generation Error',
                                   table_html="",
                                   error_message="The bot generated content, but it was not recognized as a valid HTML table."), 200
        
        app.logger.info("/generate_html_table: Successfully generated HTML table string. Rendering template.")
        return render_template('html_table_template.html',
                               page_title='Generated Table',
                               table_html=raw_table_html)
    except Exception as e:
        app.logger.error(f"/generate_html_table: An unexpected error occurred during table generation: {e}", exc_info=True)
        return render_template('html_table_template.html',
                               page_title='Table Generation Error',
                               table_html="",
                               error_message=f"An unexpected error occurred during table generation: {str(e)}"), 500

@app.route("/ai/chatbot/ra/send_message", methods=["POST"]) # Corrected path
def send_message():
    # ... (function content largely unchanged, ensure logging is present)
    user_info = session.get("user")
    if not user_info:
        app.logger.warning("Unauthorized AJAX attempt to send message.")
        return jsonify({"status": "error", "error_message": "Authentication required."}), 401

    if not request.is_json:
        app.logger.warning("Invalid request format: Not JSON.")
        return jsonify({"status": "error", "error_message": "Invalid request format."}), 400

    data = request.get_json()
    user_message = data.get("message")

    if not user_message or not user_message.strip():
        app.logger.warning("Attempted to send empty message.")
        return jsonify({"status": "error", "error_message": "Cannot send an empty message."}), 400

    user_message_clean = user_message.strip()
    if 'conversation' not in session:
        session['conversation'] = []
    session['conversation'].append({'sender': 'user', 'text': user_message_clean})
    session.modified = True

    if user_message_clean.lower() == "help":
        app.logger.info(f"User '{user_info.get('preferred_username')}' sent 'help'. Providing hardcoded response.")
        bot_answer = help_text
        session['conversation'].append({'sender': 'bot', 'text': bot_answer})
        session.modified = True
        return jsonify({"status": "success", "bot_message": bot_answer})
    else:
        thread_id = session.get('thread_id')
        if not thread_id:
            thread_id = str(uuid.uuid4())
            session['thread_id'] = thread_id
            app.logger.info(f"Generated new thread ID for session: {thread_id}")

        headers = {
            'Content-Type': 'application/json',
            'Ocp-Apim-Subscription-Key': API_SUBSCRIPTION_KEY
        }
        payload = {
            "thread_id": thread_id,
            "message": user_message_clean
        }

        try:
            app.logger.info(f"Sending message to API ({API_URL}) for thread {thread_id}. User: {user_info.get('oid')}")
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            api_response_data = response.json()
            app.logger.debug(f"API Raw Response: {api_response_data}")
            bot_answer = api_response_data.get('answer')

            if bot_answer:
                session['conversation'].append({'sender': 'bot', 'text': bot_answer})
                session.modified = True
                app.logger.info(
                    f"API call successful. Added bot response to conversation. Thread: {thread_id}")
                return jsonify({"status": "success", "bot_message": bot_answer})
            else:
                app.logger.warning(
                    f"API call successful (Status: {response.status_code}) but 'answer' field was missing or empty. Thread: {thread_id}")
                bot_placeholder_message = "[Received empty response from bot]"
                session['conversation'].append(
                    {'sender': 'bot', 'text': bot_placeholder_message})
                session.modified = True
                return jsonify({
                    "status": "success",
                    "bot_message": bot_placeholder_message,
                    "warning": "Bot response was empty"
                })
        except ValueError: 
            response_text_snippet = "N/A"
            status_code_for_log = "N/A"
            if 'response' in locals() and hasattr(response, 'text'):
                response_text_snippet = response.text[:500]
            if 'response' in locals() and hasattr(response, 'status_code'):
                status_code_for_log = response.status_code

            app.logger.error(
                f"API call successful (Status: {status_code_for_log}) but response was not valid JSON. Thread: {thread_id}. Response text: {response_text_snippet}",
                exc_info=True
            )
            error_msg = "Received an invalid response format from the bot."
            session['conversation'].append({'sender': 'system', 'text': f'[Error: {error_msg}]'})
            session.modified = True
            return jsonify({"status": "error", "error_message": error_msg}), 502
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            error_message = f"API Error: Status Code {status_code}."
            try:
                # Try to get the full error response
                error_body = http_err.response.json()
                app.logger.error(f"API Error Response Body: {error_body}")
                error_message += f" Details: {error_body}"
            except:
                error_message += f" Details: {http_err.response.text[:500]}"
    # ... rest of error handling
        except requests.exceptions.RequestException as req_err:
            error_msg = f"Failed to connect to the bot due to a network error: {req_err}"
            app.logger.error(f"Request error calling API: {req_err}", exc_info=True)
            session['conversation'].append({'sender': 'system', 'text': '[Error: Network/Connection Issue]'})
            session.modified = True
            return jsonify({"status": "error", "error_message": error_msg}), 504
        except Exception as e:
            error_msg = f"An unexpected application error occurred: {e}"
            app.logger.error(f"Unexpected error: {e}", exc_info=True)
            session['conversation'].append({'sender': 'system', 'text': '[Error: Application Error]'})
            session.modified = True
            return jsonify({"status": "error", "error_message": error_msg}), 500

@app.route("/ai/chatbot/ra/new_chat") # Corrected path
def new_chat():
    # ... (rest of the function is unchanged)
    user_info = session.get("user")
    if not user_info:
        return redirect(url_for("login"))

    session.pop("conversation", None)
    session.pop("thread_id", None)
    session.modified = True
    app.logger.info(
        f"User '{user_info.get('preferred_username')}' (oid: {user_info.get('oid')}) started a new chat.")
    flash("New chat started. Your previous conversation has been cleared.", "info")
    return redirect(url_for("index"))

@app.route('/')
def health_check():
    return 'Healthy'

if __name__ == "__main__":
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 5000)) # Azure Web Apps will use its own port, this is for local
    debug_mode_str = os.getenv('FLASK_DEBUG', '1') # Enable debug for local development
    debug_mode = debug_mode_str.lower() in ('true', '1', 't')
    
    # app.run() is for local development. Azure Web Apps uses a production WSGI server like Gunicorn.
    app.run(host=host, port=port, debug=debug_mode)