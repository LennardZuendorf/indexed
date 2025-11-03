"""Unified Jira document converter supporting both Cloud and Server/DC instances.

This module consolidates the previously separate JiraCloudDocumentConverter and
JiraDocumentConverter into a single implementation, following DRY principles.

The main difference between Cloud and Server is that Cloud uses ADF (Atlassian Document Format)
for descriptions and comments, while Server uses plain text or HTML. This unified converter
handles both formats automatically.
"""

from langchain.text_splitter import RecursiveCharacterTextSplitter


class UnifiedJiraDocumentConverter:
    """Unified converter for Jira Cloud and Server/DC documents.

    This class replaces the separate JiraCloudDocumentConverter and JiraDocumentConverter
    classes, consolidating ~92% duplicate code into a single implementation.

    The converter automatically detects whether content is in ADF format (Cloud) or
    plain text (Server) and processes it accordingly.

    Args:
        chunk_size: Size of text chunks for splitting (default: 1000)
        chunk_overlap: Overlap between chunks (default: 100)

    Example:
        >>> converter = UnifiedJiraDocumentConverter()
        >>> documents = converter.convert(jira_issue)
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """Initialize the unified Jira document converter.

        Args:
            chunk_size: Size of text chunks for splitting
            chunk_overlap: Overlap between consecutive chunks
        """
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def convert(self, document: dict) -> list:
        """Convert a Jira document to indexed format.

        Args:
            document: Jira issue document as dictionary

        Returns:
            List containing a single document dict with id, url, modifiedTime, text, and chunks
        """
        return [
            {
                "id": document["key"],
                "url": self.__build_url(document),
                "modifiedTime": document["fields"]["updated"],
                "text": self.__build_document_text(document),
                "chunks": self.__split_to_chunks(document),
            }
        ]

    def __build_document_text(self, document: dict) -> str:
        """Build complete document text from issue info, description, and comments."""
        main_info = self.__build_main_ticket_info(document)
        description_and_comments = self.__fetch_description_and_comments(document)
        return self.__convert_to_text([main_info, description_and_comments])

    def __split_to_chunks(self, document: dict) -> list:
        """Split document into chunks for indexing.

        The first chunk contains the main ticket info (key and summary).
        Additional chunks contain split description and comments.
        """
        chunks = [{"indexedData": self.__build_main_ticket_info(document)}]

        description_and_comments = self.__fetch_description_and_comments(document)
        if description_and_comments:
            for chunk in self.text_splitter.split_text(description_and_comments):
                chunks.append({"indexedData": chunk})

        return chunks

    def __fetch_description_and_comments(self, document: dict) -> str:
        """Fetch and combine description and comments.

        Automatically detects ADF format (Cloud) vs plain text (Server).
        """
        description = self.__fetch_description(document)
        comments = self.__fetch_comments(document)
        return self.__convert_to_text([description] + comments).strip()

    def __fetch_description(self, document: dict) -> str:
        """Fetch and parse description field.

        Handles both ADF (Cloud) and plain text (Server) formats.
        """
        description = document.get("fields", {}).get("description")
        if not description:
            return ""

        # Check if description is ADF format (Cloud) or plain text (Server)
        if isinstance(description, dict):
            # ADF format (Jira Cloud)
            return self.__parse_adf_content(description)
        else:
            # Plain text or HTML (Jira Server/DC)
            return str(description) if description else ""

    def __fetch_comments(self, document: dict) -> list:
        """Fetch and parse comments.

        Handles both ADF (Cloud) and plain text (Server) formats.
        """
        comments_data = document.get("fields", {}).get("comment", {}).get("comments", [])
        comments = []

        for comment in comments_data:
            body = comment.get("body")
            if not body:
                continue

            # Check if comment is ADF format (Cloud) or plain text (Server)
            if isinstance(body, dict):
                # ADF format (Jira Cloud)
                parsed = self.__parse_adf_content(body)
            else:
                # Plain text or HTML (Jira Server/DC)
                parsed = str(body) if body else ""

            if parsed:
                comments.append(parsed)

        return comments

    def __parse_adf_content(self, adf_doc: dict) -> str:
        """Parse Atlassian Document Format (ADF) to text preserving structure.

        This method is used for Jira Cloud instances which use ADF for rich text.

        Args:
            adf_doc: ADF document as dictionary

        Returns:
            Parsed text content
        """
        if not adf_doc or not isinstance(adf_doc, dict):
            return ""
        content = adf_doc.get("content", [])
        return self.__parse_adf_nodes(content)

    def __parse_adf_nodes(self, nodes: list, depth: int = 0, block_level: bool = True) -> str:
        """Parse ADF nodes recursively.

        Args:
            nodes: List of ADF nodes
            depth: Current nesting depth (for list indentation)
            block_level: Whether we're at block level or inline level

        Returns:
            Parsed text content
        """
        texts = []
        for node in nodes or []:
            node_type = node.get("type")

            if node_type == "paragraph":
                para_text = self.__parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if para_text:
                    texts.append(para_text)

            elif node_type == "heading":
                heading_text = self.__parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if heading_text:
                    level = node.get("attrs", {}).get("level", 1)
                    texts.append(f"{'#' * int(level)} {heading_text}")

            elif node_type in ("bulletList", "orderedList"):
                list_items = self.__parse_adf_nodes(
                    node.get("content", []), depth + 1, block_level=True
                )
                if list_items:
                    texts.append(list_items)

            elif node_type == "listItem":
                item_text = self.__parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if item_text:
                    indent = "  " * depth
                    texts.append(f"{indent}- {item_text}")

            elif node_type == "codeBlock":
                code_text = self.__parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if code_text:
                    texts.append(f"```\n{code_text}\n```")

            elif node_type == "text":
                text_content = node.get("text", "")
                # Apply text formatting marks
                for mark in node.get("marks", []) or []:
                    mark_type = mark.get("type")
                    if mark_type == "strong":
                        text_content = f"**{text_content}**"
                    elif mark_type == "em":
                        text_content = f"*{text_content}*"
                    elif mark_type == "code":
                        text_content = f"`{text_content}`"
                texts.append(text_content)

            elif node_type == "hardBreak":
                texts.append("\n")

            elif "content" in node:
                # Unknown node type with content - try to parse it
                nested = self.__parse_adf_nodes(
                    node.get("content", []), depth, block_level
                )
                if nested:
                    texts.append(nested)

        # Join with appropriate delimiter based on context
        if not block_level or depth > 0:
            return "".join(texts)  # Inline content or nested content
        else:
            return "\n\n".join(filter(None, texts))  # Block-level content at root

    def __build_main_ticket_info(self, document: dict) -> str:
        """Build main ticket info string with key and summary."""
        return f"{document['key']} : {document['fields']['summary']}"

    def __convert_to_text(self, elements: list, delimiter: str = "\n\n") -> str:
        """Convert list of text elements to single string with delimiter.

        Args:
            elements: List of text strings
            delimiter: Delimiter to join elements

        Returns:
            Joined string with empty elements filtered out
        """
        return delimiter.join([element for element in elements if element]).strip()

    def __build_url(self, document: dict) -> str:
        """Build browse URL for the Jira issue.

        Args:
            document: Jira issue document

        Returns:
            Browse URL for the issue
        """
        base_url = document["self"].split("/rest/api/")[0]
        return f"{base_url}/browse/{document['key']}"
