# GraphQL запрос
query = """
query getGlobalSearchResults(
  $searchString: String!,
  $items: [SearchItem]!,
  $page: PagingInput!) {
  globalSearch {
    searchByText(searchString: $searchString, items: $items, page: $page) {
    profiles {
      ...GlobalSearchProfilesSearchResult
      __typename
    }
    projects {
      ...GlobalSearchProjectsSearchResult
      __typename
    }
    studentCourses {
      ...GlobalSearchCoursesSearchResult
      __typename
    }
    __typename
  }
  __typename
}
}
fragment GlobalSearchProfilesSearchResult on ProfilesSearchResult {
  count
  profiles {
    login
    firstName
    lastName
    level
    avatarUrl
    school {
      shortName
      __typename
    }
    __typename
  }
  __typename
}
fragment GlobalSearchProjectsSearchResult on ProjectsSearchResult {
  count
  projects {
    studentTaskId
    status
    finalPercentage
    finalPoint
    project {
      goalId
      goalName
      __typename
    }
    executionType
    __typename
  }
  __typename
}
fragment GlobalSearchCoursesSearchResult on CoursesSearchResult {
  count
  courses {
    goalId
    name
    displayedCourseStatus
    executionType
    finalPercentage
    experience
    courseType
    localCourseId
    goalStatus
    __typename
  }
  __typename
}
"""
