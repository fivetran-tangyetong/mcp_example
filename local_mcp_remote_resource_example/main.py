from weather import mcp

import tools.tools

if __name__ == "__main__":
    # Initialize and run the server
    print("Starting server...")
    mcp.run(transport='stdio')
    