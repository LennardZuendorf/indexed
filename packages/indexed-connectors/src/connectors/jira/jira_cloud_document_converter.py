from langchain.text_splitter import RecursiveCharacterTextSplitter


class JiraCloudDocumentConverter:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
        )

    def convert(self, document):
        return [
            {
                "id": document["key"],
                "url": self.__build_url(document),
                "modifiedTime": document["fields"]["updated"],
                "text": self.__build_document_text(document),
                "chunks": self.__split_to_chunks(document),
            }
        ]

    def __build_document_text(self, document):
        main_info = self.__build_main_ticket_info(document)
        description_and_comments = self.__fetch_description_and_comments(document)
        return self.__convert_to_text([main_info, description_and_comments])

    def __split_to_chunks(self, document):
        chunks = [{"indexedData": self.__build_main_ticket_info(document)}]
        description_and_comments = self.__fetch_description_and_comments(document)
        if description_and_comments:
            for chunk in self.text_splitter.split_text(description_and_comments):
                chunks.append({"indexedData": chunk})
        return chunks

    def __fetch_description_and_comments(self, document):
        description = self.__fetch_description(document)
        comments = [
            self.__parse_adf_content(comment.get("body"))
            for comment in document.get("fields", {}).get("comment", {}).get("comments", [])
        ]
        return self.__convert_to_text([description] + comments)

    def __fetch_description(self, document):
        description = document.get("fields", {}).get("description")
        if not description:
            return ""
        return self.__parse_adf_content(description)

    def __parse_adf_content(self, adf_doc):
        """Parse Atlassian Document Format (ADF) to text preserving structure."""
        if not adf_doc or not isinstance(adf_doc, dict):
            return ""
        content = adf_doc.get("content", [])
        return self.__parse_adf_nodes(content)

    def __parse_adf_nodes(self, nodes, depth=0, block_level=True):
        texts = []
        for node in nodes or []:
            node_type = node.get("type")
            if node_type == "paragraph":
                para_text = self.__parse_adf_nodes(node.get("content", []), depth, block_level=False)
                if para_text:
                    texts.append(para_text)
            elif node_type == "heading":
                heading_text = self.__parse_adf_nodes(node.get("content", []), depth, block_level=False)
                if heading_text:
                    level = node.get("attrs", {}).get("level", 1)
                    texts.append(f"{'#' * int(level)} {heading_text}")
            elif node_type in ("bulletList", "orderedList"):
                list_items = self.__parse_adf_nodes(node.get("content", []), depth + 1, block_level=True)
                if list_items:
                    texts.append(list_items)
            elif node_type == "listItem":
                item_text = self.__parse_adf_nodes(node.get("content", []), depth, block_level=False)
                if item_text:
                    indent = "  " * depth
                    texts.append(f"{indent}- {item_text}")
            elif node_type == "codeBlock":
                code_text = self.__parse_adf_nodes(node.get("content", []), depth, block_level=False)
                if code_text:
                    texts.append(f"```\n{code_text}\n```")
            elif node_type == "text":
                text_content = node.get("text", "")
                for mark in node.get("marks", []) or []:
                    t = mark.get("type")
                    if t == "strong":
                        text_content = f"**{text_content}**"
                    elif t == "em":
                        text_content = f"*{text_content}*"
                    elif t == "code":
                        text_content = f"`{text_content}`"
                texts.append(text_content)
            elif node_type == "hardBreak":
                texts.append("\n")
            elif "content" in node:
                nested = self.__parse_adf_nodes(node.get("content", []), depth, block_level)
                if nested:
                    texts.append(nested)
        
        # Join with appropriate delimiter based on context
        if not block_level or depth > 0:
            return "".join(texts)  # Inline content or nested content
        else:
            return "\n\n".join(filter(None, texts))  # Block-level content at root

    def __build_main_ticket_info(self, document):
        return f"{document['key']} : {document['fields']['summary']}"


    def __convert_to_text(self, elements, delimiter="\n\n"):
        return delimiter.join([element for element in elements if element]).strip()

    def __build_url(self, document):
        base_url = document["self"].split("/rest/api/")[0]
        return f"{base_url}/browse/{document['key']}"
