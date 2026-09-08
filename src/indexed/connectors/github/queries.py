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

# include_comments=False variant: identical to ISSUES_QUERY but omits the
# comments sub-selection, so a document/comment-count-only run doesn't spend
# GraphQL rate-limit budget fetching text the converter will discard anyway.
ISSUES_QUERY_NO_COMMENTS = """
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
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

PULL_REQUESTS_QUERY = """
query PullRequests($owner: String!, $name: String!, $first: Int!, $after: String,
                    $states: [PullRequestState!], $labels: [String!]) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $first, after: $after, states: $states, labels: $labels,
                 orderBy: {field: UPDATED_AT, direction: ASC}) {
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

PULL_REQUESTS_QUERY_NO_COMMENTS = """
query PullRequests($owner: String!, $name: String!, $first: Int!, $after: String,
                    $states: [PullRequestState!], $labels: [String!]) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $first, after: $after, states: $states, labels: $labels,
                 orderBy: {field: UPDATED_AT, direction: ASC}) {
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
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

PROJECT_ITEMS_QUERY = """
query ProjectItems($login: String!, $number: Int!, $first: Int!, $after: String) {
  organization(login: $login) {
    projectV2(number: $number) {
      items(first: $first, after: $after) {
        nodes {
          id
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
          content {
            __typename
            ... on Issue {
              id number title body state url updatedAt createdAt
              author { login }
              repository { owner { login } name }
              labels(first: 50) { nodes { name } }
              comments(first: 100) { nodes { author { login } body createdAt } }
            }
            ... on PullRequest {
              id number title body state url updatedAt createdAt
              author { login }
              repository { owner { login } name }
              labels(first: 50) { nodes { name } }
              comments(first: 100) { nodes { author { login } body createdAt } }
            }
            ... on DraftIssue {
              title
              body
              createdAt
              updatedAt
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

PROJECT_ITEMS_QUERY_NO_COMMENTS = PROJECT_ITEMS_QUERY.replace(
    "\n              comments(first: 100) { nodes { author { login } body createdAt } }",
    "",
)

# User-owned (not organization-owned) Projects v2 use the identical shape under `user(login:)`.
PROJECT_ITEMS_QUERY_USER = PROJECT_ITEMS_QUERY.replace(
    "organization(login: $login)", "user(login: $login)"
)
PROJECT_ITEMS_QUERY_USER_NO_COMMENTS = PROJECT_ITEMS_QUERY_NO_COMMENTS.replace(
    "organization(login: $login)", "user(login: $login)"
)
