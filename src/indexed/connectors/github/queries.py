"""GraphQL query strings for the GitHub connector."""

ISSUES_QUERY = """
query Issues($owner: String!, $name: String!, $first: Int!, $after: String,
              $states: [IssueState!], $labels: [String!], $since: DateTime) {
  repository(owner: $owner, name: $name) {
    issues(first: $first, after: $after, states: $states, labels: $labels,
           filterBy: {since: $since}, orderBy: {field: UPDATED_AT, direction: ASC}) {
      nodes {
        id
        number
        title
        body
        state
        url
        updatedAt
        createdAt
        author { login }
        labels(first: 50) { nodes { name } }
        comments(first: 100) {
          nodes { author { login } body createdAt }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
