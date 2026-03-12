import pickle
import copy

def load_history(pkl_path):
    """Load review history from pickle file safely."""
    try:
        with open(pkl_path, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        raise RuntimeError(f"Failed to load pickle: {e}")

def save_history(pkl_path, history):
    """Save review history back to pickle."""
    with open(pkl_path, 'wb') as f:
        pickle.dump(history, f)

def iterate_user_model(history):
    """Yield (user_entry, model_entry) safely from history."""
    for i in range(0, len(history) - 1, 2):
        user_entry = history[i]
        model_entry = history[i + 1]
        yield user_entry, model_entry

def deduplicate_history(history):
    """Remove duplicate user prompts and keep corresponding model responses."""
    seen = set()
    cleaned = []
    for user_entry, model_entry in iterate_user_model(history):
        if hasattr(user_entry, "parts") and len(user_entry.parts) > 0:
            text = user_entry.parts[0].text
            if text in seen:
                continue
            if len(model_entry.parts) == 0:
                break
            seen.add(text)
            user_entry.parts = [user_entry.parts[0]]  # keep only first part
            cleaned.append(user_entry)
            cleaned.append(model_entry)
    return cleaned

def history_to_text(history):
    """Convert user/model history into readable text."""
    seen = set()
    text_out = ""
    for user_entry, model_entry in iterate_user_model(history):
        if hasattr(user_entry, "parts") and len(user_entry.parts) > 0:
            user_text = user_entry.parts[0].text.strip()
            if not user_text or user_text in seen:
                continue
            seen.add(user_text)
            text_out += f"{user_text}\n"
            if hasattr(model_entry, "parts") and len(model_entry.parts) > 0:
                model_text = model_entry.parts[0].text.strip()
                text_out += f"{model_text}\n\n"
    return text_out

def append_history(pkl_path, user_prompt, system_response):
    """Append a new user/model entry using a template from existing history."""
    history = load_history(pkl_path)

    # Find templates
    template_user = next((e for e in history if getattr(e, "role", None)=="user"), None)
    template_model = next((e for e in history if getattr(e, "role", None)=="model"), None)

    if not template_user or not template_model:
        raise ValueError("No user/model template found in pickle")

    new_user = copy.deepcopy(template_user)
    new_model = copy.deepcopy(template_model)

    new_user.parts[0].text = user_prompt
    new_model.parts[0].text = system_response

    history.append(new_user)
    history.append(new_model)
    save_history(pkl_path, history)
    return history