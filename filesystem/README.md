# MCP Filesystem Server

A secure Model Context Protocol (MCP) server that provides filesystem operations with configurable access controls.

## Features

- **Secure Operations**: All file operations are restricted to explicitly allowed directories
- **Comprehensive File Operations**:
  - Read single or multiple files
  - Write and edit files
  - Create directories
  - List directory contents
  - Move/rename files
  - Search for files
  - Get file metadata

## Installation

### Prerequisites

- Node.js 16 or higher
- npm or yarn

### Setup

1. Clone this repository
2. Navigate to the filesystem directory:
```bash
cd filesystem
```

3. Install dependencies and build:
```bash
npm install
npm run build
```

## Usage

### Starting the Server

The server requires at least one allowed directory path as an argument:

```bash
# Allow access to a single directory
node dist/index.js /path/to/allowed/directory

# Allow access to multiple directories
node dist/index.js /path/to/dir1 /path/to/dir2 ~/Documents
```

### Integration with MCP Clients

Add the server to your MCP client configuration. For example, in Claude Desktop:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "node",
      "args": ["/path/to/filesystem/dist/index.js", "/path/to/allowed/directory"]
    }
  }
}
```

## Available Tools

### read_file
Read the complete contents of a file. Automatically detects and parses various file formats.

### read_multiple_files
Read multiple files in one operation. More efficient than reading files individually.

### write_file
Create a new file or overwrite an existing file with the provided content.

### edit_file
Make line-based edits to a text file with automatic diff generation.

### create_directory
Create a new directory or ensure a directory exists.

### list_directory
Get a detailed listing of files and directories in a specified path.

### directory_tree
Get a recursive tree view of files and directories as a JSON structure.

### move_file
Move or rename files and directories.

### search_files
Recursively search for files and directories matching a pattern.

### get_file_info
Retrieve detailed metadata about a file or directory.

## Security

- All file operations are strictly limited to the allowed directories specified at startup
- Symlinks are resolved to ensure they don't point outside allowed directories
- Path traversal attempts are blocked
- Comprehensive error handling for safe operation

## Development

### Building

```bash
npm run build
```

### Development Mode

```bash
npm run dev
```

### Testing

```bash
npm test
```

## Dependencies

### Node.js Dependencies
- @modelcontextprotocol/sdk - MCP SDK for building servers
- zod - Schema validation
- diff - For generating file diffs
- minimatch - For glob pattern matching



## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 