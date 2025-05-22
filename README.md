# Project allows document indexing in vector database and then search (supports Jira and Confluence)

Currently, it supports Jira (a ticket is a document) and Confluence (a page is a document).
Does NOT send any data to any third-party systems. All data are processed locally and stored locally (except in the case when you use it as MCP with a non-local AI agent).
Supports MCP protocol to use the vector search as a tool in AI agents.
Provides abstraction to add more data sources.

Uses:
- "FAISS" lib (https://github.com/facebookresearch/faiss) for vector search;
- "sentence-transformers" lib (https://pypi.org/project/sentence-transformers/) for embeddings.

Despite the used dependencies, the project allows easy switching to other technologies.

Please check this article for more context: https://medium.com/@shnax0210/mcp-tool-for-vector-search-in-confluence-and-jira-6beeade658ba

## Common use case
1) You create a collection by dedicated script (there are separate scripts for Jira and Confluence cases). During the collection creation, data are loaded into your local machine and then indexed. Results are stored in a subfolder of `./data/collections` with name that you specify via the "--collection ${collectionName}" parameter. So collection is just a folder with all needed information for search, such as: loaded documents, index files, metadata, etc. Once a collection is created, it can be used for search and update. The creation process can take a while; it depends on the number of documents your collection consists of and local machine resources.
2) After some time, you may want to update existing collections to get new data, you can do it via a dedicated script. You will need to specify the collection name used during collection creation. Collection update reads and indexes only new/updated documents, so it should be much faster than collection creation.
3) You can search in an existing collection by dedicated script.
4) You can set up MCP tool for existing collections, so an AI agent will be able to use the search.

You can create different collections for different use cases. For example, you can create a collection for all Confluence pages to do a general search, and you can create a collection for pages from a specific Confluence space, so you will do a more narrow search.

## How to set up and use

1) Clone the repository
3) Install `uv`: https://docs.astral.sh/uv/
4) Navigate to the root project folder and run: `uv sync`

### To create collection for Confluence:

1) Set CONF_TOKEN env variable with your Confluence Bearer token (optionally, you can set CONF_LOGIN and CONF_PASSWORD env variables instead with your Confluence user login and password, but the token variant is more recommended).
2) Run command like:
```
uv run confluence_collection_create_cmd_adapter.py --collection "confluence" --url "${baseConfluenceUrl}" --cql "${confluenceQuery}"
```

Notes:
- you can use different values for the "collection" parameter, but you will need to use the same value during collection updates and searches. It defines the collection name, and all collection data will be stored in a folder with the name under `./data/collections`;
- please update ${baseConfluenceUrl} to real Confluence base url, example: https://confluence.example.com ;
- please update ${confluenceQuery} to real Confluence query, example: (type = 'page') AND (space = 'MySpace Name') AND (created >= '2024-01-14' OR lastModified >= '2024-01-14')

### To create collection for Jira:

1) Set JIRA_TOKEN env variable with your Jira Bearer token (optionally, you can set JIRA_LOGIN and JIRA_PASSWORD env variables instead with your Jira user login and password, but the token variant is more recommended).
2) Run command like:
```
uv run jira_collection_create_cmd_adapter.py --collection "jira" --url "${baseJiraUrl}" --jql "${jiraQuery}"
```

Notes:
- you can use different values for the "collection" parameter, but you will need to use the same value during collection updates and searches. It defines the collection name, and all collection data will be stored in a folder with the name under `./data/collections`;
- please update ${baseJiraUrl} to real Jira base url, example: https://jira.example.com
- please update ${jiraQuery} to real Jira query, example: project = PMCCP AND created >= -365d 

### To update existing collection:

1) Collection update reads only new information, so it should be much faster than collection creation. 
Collection update uses information from collection manifest file located in `./data/collections/${collectionName}/manifest.json`. 

If you update Confluence collection: set CONF_TOKEN env variable with your Confluence Bearer token (optionally, you can set CONF_LOGIN and CONF_PASSWORD env variables instead with your Confluence user login and password, but the token variant is more recommended).

If you update Jira collection: set JIRA_TOKEN env variable with your Jira Bearer token (optionally, you can set JIRA_LOGIN and JIRA_PASSWORD env variables instead with your Jira user login and password, but the token variant is more recommended).
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
- please update ${collectionName} to real collection name (the one used during collection creation), for example: "confluence" or "jira";
- please update ${searchQuery} to test that you would like to search, for example: "How to set up react project locally";
- you can add "--includeMatchedChunksText" paramter to include matched chunks of a document text in search results.

### To set up MCP:

Add MCP configuration like:
```
{
    "servers": {
        ...
        "search_${collectionName}_stdio": {
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

If you use VS code IDE and GitHub Copilot, you can add the configuration into `.vscode/mcp.json` file in the root of your project.
You can check more details on youtube:
- https://www.youtube.com/watch?v=VePxCcF99w4
- https://www.youtube.com/watch?v=iS25RFups4A

Notes:
- please update ${collectionName} to real collection name (the one used during collection creation), for example: "confluence" or "jira"
- please update ${fullPathToRootProjectFolder} to real full path to this project root folder.
- it can be very usefull to increase number of returned results by setting "--maxNumberOfResults ${number}", bigger number - better search, but too big number breaks GitHub Copilot, probably it's just does not fit into model context window. For Jira the parameter can be set for example to 50-70, for Confluence it's better to keep it in range 10-30.

## Collection structure
Collection is a subfolder of `./data/collections` folder.
Collection folder contains all files needed for performing vectore search in the collection.

Collection folder consists from:
- `documents` folder contains documents read by `reader` from `./main/sources` package and converted by `converter` from `./main/sources` package.
- `indexes` folder contains available indexes (usually just one index but multiple are also supported);
- `manifest.json` file contains information about index such as (name, last update time, reader details, indexes)

Please check `./main/core/documents_collection_creator.py` code to find most of details about collection creation or updating.

Please check `./main/core/documents_collection_searcher.py` code to find most of details about searching in collection.