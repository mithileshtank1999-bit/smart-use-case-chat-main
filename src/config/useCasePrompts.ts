export interface UseCase {
  label: string;
  prompt: string;
}

export interface UseCaseCategory {
  label: string;
  icon: string;
  useCases: UseCase[];
}

export const useCaseCategories: UseCaseCategory[] = [
  {
    label: "Project Planning Intelligence",
    icon: "LayoutDashboard",
    useCases: [
      {
        label: "Individual Project Milestones Summary",
        // Keep user-visible prompt short; the backend applies the detailed PMO formatting instructions.
        prompt: "Individual Project Milestones Summary for project {project_name}",
      },
      { label: "Portfolio Project Milestones Summary", prompt: "Retrieve Portfolio Project Milestones Summary from my portal for portfolio {portfolio_name}" },
      { label: "Organization Project Milestones Summary", prompt: "Retrieve Organization Project Milestones Summary from my portal" },
      { label: "Individual Project Health Status", prompt: "Individual Project Health Status Summary for project {project_name}" },
      { label: "Portfolio Project Health Status", prompt: "Retrieve Portfolio Project Health Status Summary from my portal for portfolio {portfolio_name}" },
      { label: "Organization Project Health Status", prompt: "Retrieve Organization Project Health Status Summary from my portal" },
      { label: "Individual Project Risk Indicators", prompt: "Individual Project Risk Indicators Summary for project {project_name}" },
      { label: "Portfolio Project Risk Indicators", prompt: "Retrieve Portfolio Project Risk Indicators Summary from my portal for portfolio {portfolio_name}" },
      { label: "Organization Project Risk Indicators", prompt: "Retrieve Organization Project Risk Indicators Summary from my portal" },
      { label: "Retrieve Action Centre Points", prompt: "Retrieve Action Centre Points from my portal for project {project_name} / module {module_name}" },
      { label: "Retrieve Risk", prompt: "Retrieve Risk from my portal for project {project_name} / module {module_name}" },
      { label: "Add New Action Point", prompt: "Add a new Action Point on project {project_name} / module {module_name}" },
      { label: "Add New Risk", prompt: "Add a new Risk on project {project_name} / module {module_name}" },
      { label: "Update Existing Action Point", prompt: "Update Status and comments on Existing Action Point on project {project_name} / module {module_name}" },
      { label: "Update Existing Risk", prompt: "Update Status and comments on Existing Risk on project {project_name} / module {module_name}" },
      { label: "Map Resource to Project", prompt: "Add a resource to map on project {project_name}" },
    ],
  },
  {
    label: "Timesheet Management",
    icon: "Clock",
    useCases: [
      { label: "Timesheet Entry & Submission", prompt: "Submit Timesheet Entry and Submission in my portal for employee {employee_name} on date {date}" },
      { label: "Individual Employee Timesheet Summary", prompt: "Retrieve Individual Employee Timesheet Summary from my portal for employee {employee_name}" },
      { label: "Model-wise Timesheet Booking Summary", prompt: "Retrieve Model-wise Timesheet Booking Summary from my portal for model {model_name}" },
      { label: "Project-wise Timesheet Booking Summary", prompt: "Retrieve Project-wise Timesheet Booking Summary from my portal for project {project_name}" },
      { label: "Account-wise Timesheet Booking Summary", prompt: "Retrieve Account-wise Timesheet Booking Summary from my portal for account {account_name}" },
      { label: "Portfolio-wise Timesheet Booking Summary", prompt: "Retrieve Portfolio-wise Timesheet Booking Summary from my portal for portfolio {portfolio_name}" },
      { label: "Organization-wise Timesheet Booking Summary", prompt: "Retrieve Organization-wise Timesheet Booking Summary from my portal" },
      { label: "Auto-Generate Pending Timesheet Report", prompt: "Auto-Generate Pending Timesheet Booking Report from my portal" },
    ],
  },
  {
    label: "Defect & Case Management",
    icon: "Bug",
    useCases: [
      { label: "DEV Case ID Summary", prompt: "Retrieve DEV Case ID Summary from my portal for case {case_id}" },
      { label: "DEV Module-wise Case Summary", prompt: "Retrieve DEV Module-wise Case Summary from my portal for module {module_name}" },
      { label: "DEV Journey Wise Case Summary", prompt: "Retrieve DEV Journey Wise Case Summary from my portal for journey {journey_name}" },
      { label: "DEV Project Wise Case Summary", prompt: "Retrieve DEV Project Wise Case Summary from my portal for project {project_name}" },
      { label: "SIT Case ID Summary", prompt: "Retrieve SIT Case ID Summary from my portal for case {case_id}" },
      { label: "SIT Module-wise Case Summary", prompt: "Retrieve SIT Module-wise Case Summary from my portal for module {module_name}" },
      { label: "SIT Journey Wise Case Summary", prompt: "Retrieve SIT Journey Wise Case Summary from my portal for journey {journey_name}" },
      { label: "SIT Project Wise Case Summary", prompt: "Retrieve SIT Project Wise Case Summary from my portal for project {project_name}" },
      { label: "UAT Case ID Summary", prompt: "Retrieve UAT Case ID Summary from my portal for case {case_id}" },
      { label: "UAT Module-wise Case Summary", prompt: "Retrieve UAT Module-wise Case Summary from my portal for module {module_name}" },
      { label: "UAT Journey Wise Case Summary", prompt: "Retrieve UAT Journey Wise Case Summary from my portal for journey {journey_name}" },
      { label: "UAT Project Wise Case Summary", prompt: "Retrieve UAT Project Wise Case Summary from my portal for project {project_name}" },
      { label: "Auto DEV SR/CASE Categorization Update", prompt: "Auto DEV SR/CASE Categorization Update in my portal" },
      { label: "Auto SIT SR/CASE Categorization Update", prompt: "Auto SIT SR/CASE Categorization Update in my portal" },
      { label: "Auto UAT SR/CASE Categorization Update", prompt: "Auto UAT SR/CASE Categorization Update in my portal" },
      { label: "Auto DEV SR/CASE Status & Fields Update", prompt: "Auto DEV SR/CASE Status and Fields Update in my portal" },
      { label: "Auto SIT SR/CASE Status & Fields Update", prompt: "Auto SIT SR/CASE Status and Fields Update in my portal" },
      { label: "Auto UAT SR/CASE Status & Fields Update", prompt: "Auto UAT SR/CASE Status and Fields Update in my portal" },
      { label: "DEV Module-wise Defect Summary Report", prompt: "Generate DEV Module-wise Defect Summary Report from my portal" },
      { label: "SIT Module-wise Defect Summary Report", prompt: "Generate SIT Module-wise Defect Summary Report from my portal" },
      { label: "UAT Module-wise Defect Summary Report", prompt: "Generate UAT Module-wise Defect Summary Report from my portal" },
      { label: "DEV Project-wise Defect Summary Report", prompt: "Generate DEV Project-wise Defect Summary Report from my portal for project {project_name}" },
      { label: "SIT Project-wise Defect Summary Report", prompt: "Generate SIT Project-wise Defect Summary Report from my portal for project {project_name}" },
      { label: "UAT Project-wise Defect Summary Report", prompt: "Generate UAT Project-wise Defect Summary Report from my portal for project {project_name}" },
      { label: "My Portal Request Summary", prompt: "Retrieve My Portal Request Summary from my portal" },
      { label: "My Portal Request Summary Report", prompt: "Generate My Portal Request Summary Report from my portal" },
      { label: "Travel Desk Request Summary", prompt: "Retrieve Travel Desk Request Summary from my portal" },
      { label: "Travel Desk Summary Report", prompt: "Generate Travel Desk Summary Report from my portal" },
      { label: "Help Desk-IT Request Summary", prompt: "Retrieve Help Desk-IT Request Summary from my portal" },
      { label: "Help Desk-IT Request Summary Report", prompt: "Generate Help Desk-IT Request Summary Report from my portal" },
    ],
  },
  {
    label: "Test Cases Management",
    icon: "TestTube2",
    useCases: [
      { label: "DEV Test Case ID Summary", prompt: "Retrieve DEV Test Case ID Summary from my portal for test case {test_case_id}" },
      { label: "DEV Module-wise Test Case Summary", prompt: "Retrieve DEV Module-wise Test Case Summary from my portal for module {module_name}" },
      { label: "DEV Journey Wise Test Case Summary", prompt: "Retrieve DEV Journey Wise Test Case Summary from my portal for journey {journey_name}" },
      { label: "DEV Project Wise Test Case Summary", prompt: "Retrieve DEV Project Wise Test Case Summary from my portal for project {project_name}" },
      { label: "SIT Test Case ID Summary", prompt: "Retrieve SIT Test Case ID Summary from my portal for test case {test_case_id}" },
      { label: "SIT Module-wise Test Case Summary", prompt: "Retrieve SIT Module-wise Test Case Summary from my portal for module {module_name}" },
      { label: "SIT Journey Wise Test Case Summary", prompt: "Retrieve SIT Journey Wise Test Case Summary from my portal for journey {journey_name}" },
      { label: "SIT Project Wise Test Case Summary", prompt: "Retrieve SIT Project Wise Test Case Summary from my portal for project {project_name}" },
      { label: "UAT Test Case ID Summary", prompt: "Retrieve UAT Test Case ID Summary from my portal for test case {test_case_id}" },
      { label: "UAT Module-wise Test Case Summary", prompt: "Retrieve UAT Module-wise Test Case Summary from my portal for module {module_name}" },
      { label: "UAT Journey Wise Test Case Summary", prompt: "Retrieve UAT Journey Wise Test Case Summary from my portal for journey {journey_name}" },
      { label: "UAT Project Wise Test Case Summary", prompt: "Retrieve UAT Project Wise Test Case Summary from my portal for project {project_name}" },
      { label: "Auto DEV Test Cases Categorization Update", prompt: "Auto DEV Test Cases Categorization Update in my portal" },
      { label: "Auto SIT Test Cases Categorization Update", prompt: "Auto SIT Test Cases Categorization Update in my portal" },
      { label: "Auto UAT Test Cases Categorization Update", prompt: "Auto UAT Test Cases Categorization Update in my portal" },
      { label: "Auto DEV Test Cases Status & Fields Update", prompt: "Auto DEV Test Cases Status and Fields Update in my portal" },
      { label: "Auto SIT Test Cases Status & Fields Update", prompt: "Auto SIT Test Cases Status and Fields Update in my portal" },
      { label: "Auto UAT Test Cases Status & Fields Update", prompt: "Auto UAT Test Cases Status and Fields Update in my portal" },
      { label: "DEV Module-wise Test Cases Summary Report", prompt: "Generate DEV Module-wise Test Cases Summary Report from my portal" },
      { label: "SIT Module-wise Test Cases Summary Report", prompt: "Generate SIT Module-wise Test Cases Summary Report from my portal" },
      { label: "UAT Module-wise Test Cases Summary Report", prompt: "Generate UAT Module-wise Test Cases Summary Report from my portal" },
      { label: "DEV Project-wise Test Cases Summary Report", prompt: "Generate DEV Project-wise Test Cases Summary Report from my portal for project {project_name}" },
      { label: "SIT Project-wise Test Cases Summary Report", prompt: "Generate SIT Project-wise Test Cases Summary Report from my portal for project {project_name}" },
      { label: "UAT Project-wise Test Cases Summary Report", prompt: "Generate UAT Project-wise Test Cases Summary Report from my portal for project {project_name}" },
    ],
  },
  {
    label: "Intelligent Document Management",
    icon: "FileText",
    useCases: [
      { label: "Document Analysis & Summarization", prompt: "Analyze and summarize the uploaded document" },
      { label: "Key Information Search", prompt: "Search for key information from uploaded documents about {query}" },
      { label: "Text Classification & Entity Extraction", prompt: "Perform text classification, entity extraction, and sentiment analysis from the uploaded document" },
      { label: "Context Recommendation & Update", prompt: "Provide context recommendation and update from uploaded documents" },
    ],
  },
  {
    label: "Report Automation",
    icon: "FileBarChart",
    useCases: [
      { label: "Project-Wise Status Report", prompt: "Generate Project-Wise Status Report from my portal for project {project_name}" },
      { label: "Project-Wise Dashboard Report", prompt: "Generate Project-Wise Dashboard Report from my portal for project {project_name}" },
      { label: "Weekly Status Report (WSR)", prompt: "Generate Weekly Status Report (WSR) from my portal" },
      { label: "Milestone & Leadership Management Report", prompt: "Generate Milestone & Leadership Management Report from my portal" },
    ],
  },
  {
    label: "AI Meeting Summary",
    icon: "Users",
    useCases: [
      { label: "Internal Meeting Summary", prompt: "Capture and summarize internal meeting with action items and decisions from transcript {transcript}" },
      { label: "Client Meeting Summary", prompt: "Capture and summarize client meeting with action items and decisions from transcript {transcript}" },
    ],
  },
  {
    label: "Smart Issue / Risk Analysis",
    icon: "AlertTriangle",
    useCases: [
      { label: "Risk Analysis", prompt: "Analyze recurring issues, identify root causes, and predict risks based on project data {data}" },
    ],
  },
  {
    label: "Resource Allocation & Optimization",
    icon: "Settings",
    useCases: [
      { label: "Optimize Resources", prompt: "Optimize resource allocation based on skills, workload, and project priorities for project {project_name}" },
    ],
  },
];
