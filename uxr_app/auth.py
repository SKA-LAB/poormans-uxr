import streamlit as st
import uuid
import re
from uxr_app.database import get_db, create_user, get_user_by_email, update_project

def login_page(db_manager):
    st.title("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = db_manager.get_user_by_email(email)
        if user and user.password == password:  # In real app, compare hashed passwords
            st.session_state['logged_in'] = True
            st.session_state['user_id'] = user.user_id
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid credentials.")

def signup_page(db_manager):
    st.title("Create Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    if st.button("Create Account"):
        if password != confirm_password:
            st.error("Passwords do not match.")
            return
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            st.error("Please enter a valid email address.")
            return
        if db_manager.get_user_by_email(email):
            st.error("Email already exists.")
            return

        new_user = db_manager.create_user(email, password)
        st.success("Account created successfully! Please log in.")
        st.rerun()

def create_guest_user(db_manager):
    """Create a temporary guest user and return the user_id"""
    guest_email = f"guest_{uuid.uuid4().hex[:8]}@temp.uxr"
    temp_password = uuid.uuid4().hex
    user = db_manager.create_user(guest_email, temp_password)
    return user.user_id, guest_email, temp_password

def handle_authentication(state, db_manager):
    choice = st.sidebar.selectbox("Navigation", ["Login", "Create Account", "Continue as Guest"])
    
    if choice == "Login":
        login_page(db_manager)
    elif choice == "Create Account":
        signup_page(db_manager)
    else:  # Continue as Guest
        state.guest_mode = True
        state.guest_user_id, guest_email, guest_password = create_guest_user(db_manager)
        state.user_id = state.guest_user_id
        st.session_state['guest_email'] = guest_email
        st.session_state['guest_password'] = guest_password
        st.rerun()

def show_auth_modal(state, db_manager):
    with st.sidebar.expander("Authentication Required", expanded=True):
        auth_tab1, auth_tab2 = st.tabs(["Login", "Create Account"])
        
        with auth_tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", key="login_button"):
                user = db_manager.get_user_by_email(email)
                if user and user.password == password:
                    transfer_guest_data(state, db_manager, user.user_id)
                    state.login(user.user_id)
                    st.session_state['show_auth_modal'] = False
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        
        with auth_tab2:
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
            if st.button("Create Account", key="signup_button"):
                if password != confirm_password:
                    st.error("Passwords do not match.")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.error("Please enter a valid email address.")
                elif db_manager.get_user_by_email(email):
                    st.error("Email already exists.")
                else:
                    new_user = db_manager.create_user(email, password)
                    transfer_guest_data(state, db_manager, new_user.user_id)
                    state.login(new_user.user_id)
                    st.session_state['show_auth_modal'] = False
                    st.success("Account created successfully! Your work has been transferred to your new account.")
                    st.rerun()

def transfer_guest_data(state, db_manager, new_user_id):
    if state.guest_user_id:
        for project_uuid in state.guest_projects:
            project = db_manager.get_project_by_uuid(project_uuid)
            if project:
                db_manager.update_project(project_uuid, {'user_id': new_user_id})

def logout(state):
    state.logout()
    st.rerun()