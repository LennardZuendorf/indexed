# Project allows document indexing in vector database and then search

Currently, supports Jira (a ticket is a document) and Confluence (a page is a document). 
Provides abstraction to add more sources.
Supports MCP protocol to use the vector search as a tool in AI agents.

Uses:
- "FAISS" lib (https://github.com/facebookresearch/faiss) for vector search;
- "sentence-transformers" lib (https://pypi.org/project/sentence-transformers/) for embeddings.

Despite the used dependencies the project allows easy switch to other technologies.

Please check this article for more context: https://medium.com/@shnax0210/mcp-tool-for-vector-search-in-confluence-and-jira-6beeade658ba

## Hot to set up and use:

1) Clone the repository
3) Install `uv`: https://docs.astral.sh/uv/
4) Navigate to root project folder and run: `uv sync`

### To create collection for Confluence:

1) Set CONF_TOKEN env variable with your Confluence Bearer token (optionally you can set CONF_LOGIN and CONF_PASSWORD env variables instead with your Confluence user login and password, but token variant is more recommended)
2) Run command like:
```
uv run confluence_collection_create_cmd_adapter.py --collection "confluence" --url "${baseConfluenceUrl}" --cql "${confluenceQuery}"
```

Notes:
- you can use different value for "collection" parameter, but you will need to use same value during collection update and search. It defines collection name and all collection data will be stored in folder with the name in `./data`;
- please update ${baseConfluenceUrl} to real Confluence base url, example: https://confluence.example.com ;
- pelase updae ${confluenceQuery} to real Confluence query, example: (type = 'page') AND (space = 'MySpaceName') AND (created >= '2024-01-14' OR lastModified >= '2024-01-14')

### To create collection for Jira:

1) Set JIRA_TOKEN env variable with your Jira Bearer token (optionally you can set JIRA_LOGIN and JIRA_PASSWORD env variables instead with your Jira user login and password, but token variant is more recommended)
2) Run command like:
```
uv run jira_collection_create_cmd_adapter.py --collection "jira" --url "${baseJiraUrl}" --jql "${jiraQuery}"
```

Notes:
- you can use different value for "collection" parameter, but you will need to use same value during collection update and search. It defines collection name and all collection data will be stored in folder with the name in `./data`;
- please update ${baseJiraUrl} to real Jira base url, example: https://jira.example.com
- please update ${jiraQuery} to real Jira query, example: project = PMCCP AND created >= -365d

### To update existing collection:

1) Collection update reads only new information, so it should be much faster than collection creation. 
Collection update uses information from collection manifest file located in `./data/${collectionName}/manifest.json`. 
If you update Confluence collection: set CONF_TOKEN env variable with your Confluence Bearer token (optionally you can set CONF_LOGIN and CONF_PASSWORD env variables instead with your Confluence user login and password, but token variant is more recommended)
If you update Jira collection: set JIRA_TOKEN env variable with your Jira Bearer token (optionally you can set JIRA_LOGIN and JIRA_PASSWORD env variables instead with your Jira user login and password, but token variant is more recommended)
2) Run command like:
```
uv run collection_update_cmd_adapter.py --collection "${collectionName}"
```

Notes:
- please update ${collectionName} to real collection name (the one used during collection creation), for example: "confluence" or "jira"

### To search in collection:

Run command like:
```
uv run collection_search_cmd_adapter.py --collection "${collectionName}" --query "${searchQuery}"
```

Notes:
- please update ${collectionName} to real collection name (the one used during collection creation), for example: "confluence" or "jira"
- please update ${searchQuery} to test that you would like to search, for example: "How to set up react project locally"

### To set up MCP:

Add MCP configuration like:
```
{
    "servers": {
        ...
        "seach_${collectionName}_stdio": {
            "type": "stdio",
            "command": "uv",
            "args": [
                "--directory",
                "${fullPathToRootProjectFolder}",
                "run",
                "collection_search_mcp_stdio_adapter.py",
                "--collection",
                "${collectionName}",
            ]
        },
        ...
    }
}
```

If you use VS code IDE and GitHub Copilot, you can add the configuration into `.vscode/mcp.json` file in root of you project.
You can check more details on youtube:
- https://www.youtube.com/watch?v=VePxCcF99w4
- https://www.youtube.com/watch?v=iS25RFups4A

Notes:
- please update ${collectionName} to real collection name (the one used during collection creation), for example: "confluence" or "jira"
- please update ${fullPathToRootProjectFolder} to real full path to this project root folder.


## How it works

Collection is a subfolder of `./data` folder.
Collection folder contains all files needed for performing vectore search in the collection.

Please check `./main/core/documents_collection_creator.py` code to find most of details about collection creation or updating.

Please check `./main/core/documents_collection_searcher.py` code to find most of details about searching in collection.

Collection folder structure:
- `documents` folder contains documents read by `reader` from `./main/sources` package and converted by `converter` from `./main/sources` package.
- `indexes` folder contains available indexes (usually just one index but multiple are also supported);
- `manifest.json` file contains information about index such as (name, last update time, reader details, indexes)
