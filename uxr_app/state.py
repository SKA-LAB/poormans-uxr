class AppState:
    def __init__(self):
        self.logged_in = False
        self.user_id = None
        self.current_project_uuid = None
        self.guest_mode = False
        self.guest_user_id = None
        self.guest_projects = []

    def login(self, user_id):
        self.logged_in = True
        self.user_id = user_id
        self.guest_mode = False

    def logout(self):
        self.logged_in = False
        self.user_id = None
        self.current_project_uuid = None
        self.guest_mode = False
        self.guest_user_id = None