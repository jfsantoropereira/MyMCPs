# LocalMCP - Model Context Protocol Servers

A collection of local Model Context Protocol (MCP) servers for enhanced AI assistant capabilities.

## Overview

This repository contains MCP servers that can be used with AI assistants like Claude to provide additional capabilities through a standardized protocol.

## Available Servers

### Filesystem Server

Located in the `filesystem/` directory, this server provides secure filesystem access with advanced document parsing capabilities.

**Features:**
- Secure file operations restricted to allowed directories
- Support for multiple file formats (PDF, Word, Excel, PowerPoint, images, etc.)
- OCR capabilities for image-based documents
- Comprehensive file management operations

For detailed setup and usage instructions, see [filesystem/README.md](filesystem/README.md).

## Installation

Each server has its own installation requirements. Navigate to the specific server directory and follow the README instructions.

### General Requirements

- Node.js 16 or higher
- Python 3.8 or higher (for servers with Python components)
- npm or yarn

## Project Structure

```
LocalMCP/
├── filesystem/          # Filesystem MCP server
│   ├── index.ts        # Main server implementation
│   ├── parse_document.py # Document parsing utility
│   ├── package.json    # Node.js dependencies
│   ├── requirements.txt # Python dependencies
│   └── README.md       # Server documentation
└── README.md           # This file
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT
