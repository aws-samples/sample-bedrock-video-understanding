import React, { Component } from "react";
import { Select, Table, Container, Header, SpaceBetween, BarChart, Box, ColumnLayout, Spinner, Alert } from "@cloudscape-design/components";
import { FetchPost } from "../../resources/data-provider";
import { refreshThumbnailUrls } from "../../resources/thumbnail-utils";
import "./dataMain.css";

const GROUP_OPTIONS = [
  { label: "All", value: "all" },
  { label: "Frame Based", value: "frame" },
  { label: "Shot Based", value: "clip" },
  { label: "Nova MME", value: "novamme" },
  { label: "TwelveLabs", value: "tlabsmme" },
];

const formatBytes = (bytes) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
};

class DataGenerationMain extends Component {
  constructor(props) {
    super(props);
    this.state = {
      selectedGroup: { label: "All", value: "all" },
      tableData: [],
      chartData: [],
      loading: true,
      error: null,
    };
  }

  componentDidMount() {
    this.loadData();
  }

  loadData = async () => {
    this.setState({ loading: true, error: null });

    try {
      const workflowTypes = [
        { name: "Frame Based", type: "frame" },
        { name: "Shot Based", type: "clip" },
      ];

      const workflowData = await Promise.all(
        workflowTypes.map(async (workflow) => {
          // Get all tasks for this workflow type
          const tasksResponse = await FetchPost(
            "/extraction/video/search-task",
            { TaskType: workflow.type, PageSize: 1000 },
            "ExtrService"
          );

          if (tasksResponse.statusCode !== 200) {
            return null;
          }

          const tasks = await refreshThumbnailUrls(tasksResponse.body || [], "ExtrService");
          const completedTasks = tasks.filter(t => t.Status === "COMPLETED");

          // Fetch data size and cost for each completed task
          const taskDetails = await Promise.all(
            completedTasks.map(async (task) => {
              try {
                const [dataSizeRes, costRes] = await Promise.all([
                  FetchPost("/extraction/video/get-data-size", { task_id: task.TaskId }, "ExtrService"),
                  FetchPost("/extraction/video/get-token-and-cost", { task_id: task.TaskId }, "ExtrService"),
                ]);

                return {
                  dataSize: dataSizeRes.statusCode === 200 ? dataSizeRes.body?.total_size || 0 : 0,
                  computeCost: costRes.statusCode === 200 ? costRes.body?.total_cost || 0 : 0,
                };
              } catch (err) {
                return { dataSize: 0, computeCost: 0 };
              }
            })
          );

          const totalDataSize = taskDetails.reduce((sum, t) => sum + t.dataSize, 0);
          const totalComputeCost = taskDetails.reduce((sum, t) => sum + t.computeCost, 0);
          const storageCost = (totalDataSize / (1024 * 1024 * 1024)) * 0.023; // S3 Standard: $0.023/GB

          return {
            workflow: workflow.name,
            videos: completedTasks.length,
            computeCost: totalComputeCost,
            storageCost: storageCost,
            totalCost: totalComputeCost + storageCost,
            dataSize: totalDataSize,
            avgDataSize: completedTasks.length > 0 ? totalDataSize / completedTasks.length : 0,
          };
        })
      );

      const validData = workflowData.filter(d => d !== null);

      this.setState({
        tableData: validData,
        chartData: validData.map(item => ({ x: item.workflow, y: item.totalCost })),
        loading: false,
      });
    } catch (err) {
      this.setState({
        loading: false,
        error: err.message || "Failed to load data",
      });
    }
  };

  handleGroupChange = ({ detail }) => {
    this.setState({ selectedGroup: detail.selectedOption });
    // Filter data based on selection
  };

  render() {
    const { selectedGroup, tableData, chartData, loading, error } = this.state;

    if (loading) {
      return (
        <div className="data-generation-main">
          <Container>
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <Spinner size="large" />
              <Box variant="p" padding={{ top: 's' }}>Loading data generation analytics...</Box>
            </div>
          </Container>
        </div>
      );
    }

    if (error) {
      return (
        <div className="data-generation-main">
          <Container>
            <Alert type="error" header="Failed to load data">
              {error}
            </Alert>
          </Container>
        </div>
      );
    }

    return (
      <div className="data-generation-main">
        <SpaceBetween size="l">
          <Container
            header={
              <Header variant="h2" description="View analytics by workflow type">
                Data Generation Analytics
              </Header>
            }
          >
            <SpaceBetween size="m">
              <Select
                selectedOption={selectedGroup}
                onChange={this.handleGroupChange}
                options={GROUP_OPTIONS}
                placeholder="Select workflow"
              />
            </SpaceBetween>
          </Container>

          <Container header={<Header variant="h3">Cost & Data Generation Summary</Header>}>
            <Table
              columnDefinitions={[
                { id: "workflow", header: "Workflow", cell: item => item.workflow },
                { id: "videos", header: "Videos Processed", cell: item => item.videos },
                { id: "computeCost", header: "Compute Cost ($)", cell: item => item.computeCost.toFixed(2) },
                { id: "storageCost", header: "Storage Cost ($)", cell: item => item.storageCost.toFixed(2) },
                { id: "totalCost", header: "Total Cost ($)", cell: item => item.totalCost.toFixed(2) },
                { id: "dataSize", header: "Total Data Generated", cell: item => formatBytes(item.dataSize) },
                { id: "avgDataSize", header: "Avg Data per Video", cell: item => formatBytes(item.avgDataSize) },
              ]}
              items={tableData}
              loadingText="Loading data"
              empty={
                <Box textAlign="center" color="inherit">
                  <b>No data available</b>
                </Box>
              }
            />
          </Container>

          <ColumnLayout columns={2}>
            <Container header={<Header variant="h3">Cost Breakdown</Header>}>
              <BarChart
                series={[
                  {
                    title: "Compute Cost",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.computeCost })),
                  },
                  {
                    title: "Storage Cost",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.storageCost })),
                  },
                ]}
                xDomain={tableData.map(item => item.workflow)}
                yDomain={[0, Math.max(...tableData.map(d => d.totalCost)) * 1.2]}
                xTitle="Workflow"
                yTitle="Cost ($)"
                height={300}
                stackedBars
                empty={
                  <Box textAlign="center" color="inherit">
                    <b>No data available</b>
                  </Box>
                }
              />
            </Container>

            <Container header={<Header variant="h3">Data Generation Volume</Header>}>
              <BarChart
                series={[
                  {
                    title: "Data Size",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.dataSize / (1024 * 1024 * 1024) })),
                  },
                ]}
                xDomain={tableData.map(item => item.workflow)}
                yDomain={[0, Math.max(...tableData.map(d => d.dataSize / (1024 * 1024 * 1024))) * 1.2]}
                xTitle="Workflow"
                yTitle="Data Size (GB)"
                height={300}
                empty={
                  <Box textAlign="center" color="inherit">
                    <b>No data available</b>
                  </Box>
                }
              />
            </Container>
          </ColumnLayout>
        </SpaceBetween>
      </div>
    );
  }
}

export default DataGenerationMain;
