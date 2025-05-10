# Discord-Like ChatApp

## How to Run (Linux-Based Systems)

### Start the Server
Run the following command in the terminal to start the server:

```bash
./start_server
```

If the server does not start, grant execution permissions to the file:

```bash
chmod +x start_server
```

### Start the Client
Run the client using the following command:

```bash
python3 gui_client.py
```

### Login or Create an Account
Enter your username and password (or create a new account) in the `users.json` file. Example accounts:

- Username: `bao`, Password: `123`
- Username: `aob`, Password: `321`
- Username: `hacker`, Password: `456`

## Features
### Currently Available:
- User authentication
- User status updates
- Channel hosting
- Online users list
- View messages in a channel
- Send messages in a channel
- Livestreaming
- User fetch

### Communication between 2 computers:
- Use the same IP address for both computers.
- setup the server on one computer and the client on another.

