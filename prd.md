# Product Requirements Document: Indexed

## 1. Introduction & Vision

**Product Name:** Indexed

**Vision:** To provide a simple, powerful, and privacy-first search tool that allows individuals to find information within their personal digital documents. Indexed is for users who want the power of modern semantic search without sending their data to the cloud. It understands what you mean, not just what you type.

## 2. The Problem

Professionals like software developers, researchers, and writers accumulate a vast number of documents locally—project notes, code, articles, and personal knowledge bases. Finding specific information within this collection is often difficult and inefficient. Standard keyword search tools frequently miss the context or intent behind a query, leading to frustrating and irrelevant results. While cloud-based search solutions exist, they require users to upload their private data, creating significant privacy concerns.

## 3. The Solution & Target Audience

**Solution:** Indexed is a command-line tool that builds a private, local search engine for your documents. It uses modern AI techniques to understand the *meaning* of your content, delivering highly relevant results to natural language questions.

**Target Audience:**
*   **Individual Developers:** Who need to search through project documentation, code comments, and technical articles.
*   **Researchers & Academics:** Who manage large libraries of papers and notes.
*   **Technical Writers:** Who need to reference information across multiple documents.
*   **Anyone** who values data privacy and wants a more intelligent way to search their personal files.

## 4. Core Features & User Stories

This PRD covers the core functionality required to deliver a complete and valuable experience.

**User Stories:**

*   **Indexing Documents:**
    *   As a user, I want to **add a folder of documents** to my search index so the system can learn its content.
    *   As a user, I want to **give my document collections a simple name** so I can easily manage them.

*   **Searching:**
    *   As a user, I want to **search all of my documents using a simple question or phrase** and get a list of the most relevant results.
    *   As a user, I want the option to **search within a specific document collection** to narrow down my results.

*   **Managing Collections:**
    *   As a user, I want to **see a list of all my document collections** to know what's available to be searched.
    *   As a user, I want to **update a collection** to ensure the search index reflects the latest changes in my files.
    *   As a user, I want to **remove a collection** that I no longer need.

## 5. User Experience & Workflow

The primary interface is the command line, designed to be simple and intuitive.

**The core workflow is:**

1.  **Create an Index:** The user points the tool at a folder.
    *   `indexed create ./my-project-notes --name notes`

2.  **Search:** The user asks a natural language question.
    *   `indexed search "how does the authentication system work?"`

3.  **Manage:** The user can easily inspect, update, or remove what they've indexed.
    *   `indexed inspect`
    *   `indexed update notes`
    *   `indexed remove notes`

The output will be clean, human-readable, and provide clear feedback at every step.

## 6. Success Metrics

We will measure the success of Indexed based on the following criteria:

*   **Relevance:** Search results consistently and accurately answer the user's query.
*   **Simplicity:** A new user can successfully install the tool, index a collection, and perform a search in under 5 minutes.
*   **Performance:** Indexing and searching are fast enough for typical document collections, providing a smooth user experience.
*   **Privacy:** The tool operates 100% offline by default, with no data leaving the user's machine.

## 7. Future Roadmap (Out of Scope for Initial Release)

While the above features define the core product, we envision the following enhancements in the future:

*   **Enhanced User Interface:** A more visual and interactive command-line experience using tables, colors, and progress bars.
*   **Additional Data Sources:** Support for indexing content from other sources, such as Git repositories, Notion, or Confluence.
*   **Web Interface:** A simple, browser-based UI for users who prefer a graphical interface over the command line.
