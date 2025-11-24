import React, { Component } from "react";
import { Select, Table, Container, Header, SpaceBetween, BarChart, Box, ColumnLayout, Spinner, Alert } from "@cloudscape-design/components";
import { FetchPost } from "../../resources/data-provider";
import { refreshThumbnailUrls } from "../../resources/thumbnail-utils";
import pricingConfig from "../../resources/pricing-config.json";
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

const calculateCost = (usageRecords, region = 'us-east-1') => {
  if (!usageRecords || !Array.isArray(usageRecords)) return 0;

  let totalCost = 0;
  const regionPricing = pricingConfig[region] || pricingConfig['us-east-1'];

  usageRecords.forEach(record => {
    const modelId = record.model_id;
    // Handle cases where type might be missing or different
    const type = record.type;

    if (regionPricing[modelId]) {
      let pricing = null;
      // Try to find pricing by type, or fallback if structure allows
      if (type && regionPricing[modelId][type]) {
        pricing = regionPricing[modelId][type];
      } else {
        // Fallback: check if model has direct pricing keys (unlikely based on config structure but good safety)
        // or if there's only one key in the model object
        const keys = Object.keys(regionPricing[modelId]);
        if (keys.length === 1) pricing = regionPricing[modelId][keys[0]];
      }

      if (pricing) {
        let amount = 0;
        if (pricing.unit === 'token') {
          amount = ((record.input_tokens || 0) / 1000) * pricing.price_per_1k_input_tokens +
            ((record.output_tokens || 0) / 1000) * pricing.price_per_1k_output_tokens;
        } else if (pricing.unit === 'image') {
          amount = (record.number_of_image || 1) * pricing.price_per_image;
        } else if (pricing.unit === 'second') {
          amount = (record.duration || 0) * pricing.price_per_second;
        }
        totalCost += amount;
      }
    } else if (modelId === 'amazon_transcribe') {
      // Special handling for transcribe if it appears as model_id
      const pricing = regionPricing['amazon_transcribe']['transcribe'];
      if (pricing) {
        totalCost += (record.duration || 0) * pricing.price_per_second;
      }
    }
  });

  return totalCost;
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
          const completedTasks = tasks.filter(t => t.Status === "COMPLETED" || t.Status === "extraction_completed");

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
                  computeCost: costRes.statusCode === 200 ? calculateCost(costRes.body?.usage_records, costRes.body?.region) : 0,
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

      if (validData.length > 0) {
        const totalVideos = validData.reduce((sum, item) => sum + item.videos, 0);
        const totalComputeCost = validData.reduce((sum, item) => sum + item.computeCost, 0);
        const totalStorageCost = validData.reduce((sum, item) => sum + item.storageCost, 0);
        const totalCost = validData.reduce((sum, item) => sum + item.totalCost, 0);
        const totalDataSize = validData.reduce((sum, item) => sum + item.dataSize, 0);
        const avgDataSize = totalVideos > 0 ? totalDataSize / totalVideos : 0;

        validData.push({
          workflow: "Total",
          videos: totalVideos,
          computeCost: totalComputeCost,
          storageCost: totalStorageCost,
          totalCost: totalCost,
          dataSize: totalDataSize,
          avgDataSize: avgDataSize
        });
      }

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
                { id: "computeCost", header: "Token Usage & Cost ($)", cell: item => item.computeCost.toFixed(4) },
                { id: "storageCost", header: "Storage Cost ($)", cell: item => item.storageCost.toFixed(4) },
                { id: "totalCost", header: "Total Cost ($)", cell: item => item.totalCost.toFixed(4) },
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
                    title: "Token Usage & Cost",
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
