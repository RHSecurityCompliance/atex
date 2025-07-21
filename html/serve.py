#!/usr/bin/python3

import http.server
import socketserver
import time
import sys

# Define the port the server will run on.
# You can change this to any port you like.
PORT = 8000

class DelayedHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    This custom request handler inherits from SimpleHTTPRequestHandler.
    It overrides the 'do_GET', 'do_POST', and 'do_HEAD' methods to
    introduce a 1-second delay before calling the parent class's
    method to handle the request. This simulates a slow network.
    """

    def do_GET(self):
        """Handle GET requests with a 1-second delay."""
        print(f"Received GET request from {self.client_address[0]}. Introducing 1s delay...")
        time.sleep(1)
        # Call the original handler to serve the file.
        super().do_GET()

    def do_POST(self):
        """Handle POST requests with a 1-second delay."""
        print(f"Received POST request from {self.client_address[0]}. Introducing 1s delay...")
        time.sleep(1)
        # Call the original handler.
        super().do_POST()

    def do_HEAD(self):
        """Handle HEAD requests with a 1-second delay."""
        print(f"Received HEAD request from {self.client_address[0]}. Introducing 1s delay...")
        time.sleep(1)
        # Call the original handler.
        super().do_HEAD()

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    This server class uses ThreadingMixIn to handle each request in a new thread.
    This is crucial for our use case, as it prevents the server from blocking
    all other requests while one is sleeping for its 1-second delay.
    """
    # This makes the server multi-threaded.
    daemon_threads = True


if __name__ == "__main__":
    # Set the handler to our custom delayed handler.
    handler = DelayedHTTPRequestHandler

    # Create an instance of our multi-threaded server.
    # It binds to all network interfaces on the specified port.
    httpd = ThreadingHTTPServer(("", PORT), handler)

    print(f"Serving HTTP on 0.0.0.0 port {PORT} (http://0.0.0.0:{PORT}/)")
    print("Each request will be delayed by 1 second.")
    print("Press Ctrl+C to stop the server.")

    try:
        # Start the server and keep it running until interrupted.
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Handle Ctrl+C interruption gracefully.
        print("\nShutting down the server...")
        httpd.shutdown()
        sys.exit(0)
