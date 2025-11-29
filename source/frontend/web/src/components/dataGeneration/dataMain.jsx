import React, { Component } from "react";
import { Select, Table, Container, Header, SpaceBetween, BarChart, Box, ColumnLayout, Spinner, Alert, ExpandableSection } from "@cloudscape-design/components";
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
    const type = record.type;

    if (regionPricing[modelId]) {
      let pricing = null;
      if (type && regionPricing[modelId][type]) {
        pricing = regionPricing[modelId][type];
      } else {
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
      const pricing = regionPricing['amazon_transcribe']['transcribe'];
      if (pricing) {
        totalCost += (record.duration || 0) * pricing.price_per_second;
      }
    }
  });

  return totalCost;
};

const calculateInfrastructureCost = (usageRecords, region = 'us-east-1') => {
  if (!usageRecords || !Array.isArray(usageRecords)) return 0;

  const regionPricing = pricingConfig[region] || pricingConfig['us-east-1'];
  const infraPricing = regionPricing.infrastructure?.processing;

  if (!infraPricing) return 0;

  let maxDuration = 0;
  usageRecords.forEach(record => {
    const duration = parseFloat(record.duration || record.duration_s || 0);
    if (duration > maxDuration) maxDuration = duration;
  });

  return maxDuration * infraPricing.price_per_second;
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
      // Extraction service workflows (Frame Based, Shot Based)
      const extractionWorkflows = [
        { name: "Frame Based", type: "frame" },
        { name: "Shot Based", type: "clip" },
      ];

      const extractionData = await Promise.all(
        extractionWorkflows.map(async (workflow) => {
          const tasksResponse = await FetchPost(
            "/extraction/video/search-task",
            { TaskType: workflow.type, PageSize: 1000 },
            "ExtrService"
          );

          if (tasksResponse.statusCode !== 200) return null;

          const tasks = await refreshThumbnailUrls(tasksResponse.body || [], "ExtrService");
          const completedTasks = tasks.filter(t => t.Status === "COMPLETED" || t.Status === "extraction_completed");

          // Calculate source video size from task metadata
          const totalSourceVideoSize = completedTasks.reduce((sum, task) => {
            const size = parseFloat(task.MetaData?.VideoMetaData?.Size) || 0;
            return sum + size;
          }, 0);

          const workflowType = workflow.type === "frame" ? "frame_based" : "shot_based";
          const taskDetails = await Promise.all(
            completedTasks.map(async (task) => {
              try {
                const [dataSizeRes, costRes] = await Promise.all([
                  FetchPost("/extraction/video/get-data-size", { task_id: task.TaskId, workflow_type: workflowType }, "ExtrService"),
                  FetchPost("/extraction/video/get-token-and-cost", { task_id: task.TaskId }, "ExtrService"),
                ]);
                return {
                  dataSize: dataSizeRes.statusCode === 200 ? dataSizeRes.body?.total_size || 0 : 0,
                  computeCost: costRes.statusCode === 200 ? calculateCost(costRes.body?.usage_records, costRes.body?.region) : 0,
                  infraCost: costRes.statusCode === 200 ? calculateInfrastructureCost(costRes.body?.usage_records, costRes.body?.region) : 0,
                };
              } catch (err) {
                return { dataSize: 0, computeCost: 0, infraCost: 0 };
              }
            })
          );

          const totalDataSize = taskDetails.reduce((sum, t) => sum + t.dataSize, 0);
          const totalComputeCost = taskDetails.reduce((sum, t) => sum + t.computeCost, 0);
          const totalInfraCost = taskDetails.reduce((sum, t) => sum + t.infraCost, 0);
          const sourceVideoStorageCost = (totalSourceVideoSize / (1024 * 1024 * 1024)) * 0.023;
          const generatedDataStorageCost = (totalDataSize / (1024 * 1024 * 1024)) * 0.023;

          return {
            workflow: workflow.name,
            videos: completedTasks.length,
            sourceVideoSize: totalSourceVideoSize,
            computeCost: totalComputeCost,
            infraCost: totalInfraCost,
            sourceVideoStorageCost: sourceVideoStorageCost,
            generatedDataStorageCost: generatedDataStorageCost,
            totalCost: sourceVideoStorageCost + generatedDataStorageCost,
            dataSize: totalDataSize,
            avgDataSize: completedTasks.length > 0 ? totalDataSize / completedTasks.length : 0,
          };
        })
      );

      // Nova MME workflow
      const novaData = await this.loadEmbeddingWorkflowData("Nova MME", "/nova/embedding/search-task", "NovaService", "nova_mme");

      // TwelveLabs workflow
      const tlabsData = await this.loadEmbeddingWorkflowData("TwelveLabs", "/tlabs/embedding/search-task", "TLabsService", "tlabs");

      const allData = [...extractionData, novaData, tlabsData].filter(d => d !== null);

      if (allData.length > 0) {
        const totalVideos = allData.reduce((sum, item) => sum + item.videos, 0);
        const totalSourceVideoSize = allData.reduce((sum, item) => sum + item.sourceVideoSize, 0);
        const totalComputeCost = allData.reduce((sum, item) => sum + item.computeCost, 0);
        const totalInfraCost = allData.reduce((sum, item) => sum + item.infraCost, 0);
        const totalSourceVideoStorageCost = allData.reduce((sum, item) => sum + item.sourceVideoStorageCost, 0);
        const totalGeneratedDataStorageCost = allData.reduce((sum, item) => sum + item.generatedDataStorageCost, 0);
        const totalCost = allData.reduce((sum, item) => sum + item.totalCost, 0);
        const totalDataSize = allData.reduce((sum, item) => sum + item.dataSize, 0);

        allData.push({
          workflow: "Total",
          videos: totalVideos,
          sourceVideoSize: totalSourceVideoSize,
          computeCost: totalComputeCost,
          infraCost: totalInfraCost,
          sourceVideoStorageCost: totalSourceVideoStorageCost,
          generatedDataStorageCost: totalGeneratedDataStorageCost,
          totalCost: totalCost,
          dataSize: totalDataSize,
          avgDataSize: totalVideos > 0 ? totalDataSize / totalVideos : 0
        });
      }

      this.setState({
        tableData: allData,
        chartData: allData.map(item => ({ x: item.workflow, y: item.totalCost })),
        loading: false,
      });
    } catch (err) {
      this.setState({
        loading: false,
        error: err.message || "Failed to load data",
      });
    }
  };

  loadEmbeddingWorkflowData = async (name, endpoint, apiName, workflowType) => {
    try {
      const tasksResponse = await FetchPost(endpoint, { SearchText: "", PageSize: 1000, FromIndex: 0 }, apiName);
      if (tasksResponse.statusCode !== 200) return null;

      const tasks = tasksResponse.body || [];
      const completedTasks = tasks.filter(t => t.Status === "COMPLETED" || t.Status === "completed");

      // Fetch real data sizes from S3 using extraction service API
      const taskDetails = await Promise.all(
        completedTasks.map(async (task) => {
          const taskId = task.TaskId || task.Id;
          const videoSize = parseFloat(task.MetaData?.VideoMetaData?.Size) || 0;
          try {
            const dataSizeRes = await FetchPost("/extraction/video/get-data-size", { task_id: taskId, workflow_type: workflowType }, "ExtrService");
            return {
              sourceVideoSize: videoSize,
              dataSize: dataSizeRes.statusCode === 200 ? dataSizeRes.body?.total_size || 0 : 0,
            };
          } catch (err) {
            return { sourceVideoSize: videoSize, dataSize: 0 };
          }
        })
      );

      const totalSourceVideoSize = taskDetails.reduce((sum, t) => sum + t.sourceVideoSize, 0);
      const totalDataSize = taskDetails.reduce((sum, t) => sum + t.dataSize, 0);
      const sourceVideoStorageCost = (totalSourceVideoSize / (1024 * 1024 * 1024)) * 0.023;
      const generatedDataStorageCost = (totalDataSize / (1024 * 1024 * 1024)) * 0.023;

      return {
        workflow: name,
        videos: completedTasks.length,
        sourceVideoSize: totalSourceVideoSize,
        computeCost: 0,
        infraCost: 0,
        sourceVideoStorageCost: sourceVideoStorageCost,
        generatedDataStorageCost: generatedDataStorageCost,
        totalCost: sourceVideoStorageCost + generatedDataStorageCost,
        dataSize: totalDataSize,
        avgDataSize: completedTasks.length > 0 ? totalDataSize / completedTasks.length : 0,
      };
    } catch (err) {
      console.error(`Error loading ${name} data:`, err);
      return null;
    }
  };

  handleGroupChange = ({ detail }) => {
    this.setState({ selectedGroup: detail.selectedOption });
  };

  render() {
    const { selectedGroup, tableData, loading, error } = this.state;

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
            <SpaceBetween size="m">
              <ExpandableSection
                headerText="Calculation Logic"
                variant="container"
                defaultExpanded={false}
              >
                <SpaceBetween size="s">
                  <div><strong>Frame Based</strong></div>
                  <ul style={{ margin: '0', paddingLeft: '1.5rem' }}>
                    <li>S3: Extracted PNG frames, frame analysis JSON, transcription files</li>
                    <li>DynamoDB: Frame analysis records, transcript records</li>
                  </ul>
                  
                  <div><strong>Shot Based</strong></div>
                  <ul style={{ margin: '0', paddingLeft: '1.5rem' }}>
                    <li>S3: Video clips, shot analysis JSON, shot embeddings, transcription files</li>
                    <li>DynamoDB: Shot analysis records, transcript records</li>
                  </ul>
                  
                  <div><strong>Nova MME</strong></div>
                  <ul style={{ margin: '0', paddingLeft: '1.5rem' }}>
                    <li>S3: Embedding JSONL files (~26KB), manifest, metadata</li>
                    <li>S3 Vectors: Vector embeddings (~4KB per vector, 1024 dimensions × 4 bytes + metadata)</li>
                  </ul>
                  
                  <div><strong>TwelveLabs</strong></div>
                  <ul style={{ margin: '0', paddingLeft: '1.5rem' }}>
                    <li>S3: Output JSON files (~8-16KB), manifest</li>
                    <li>S3 Vectors: Vector embeddings (~4KB per vector, 1024 dimensions × 4 bytes + metadata)</li>
                  </ul>
                  
                  <Alert type="info" header="Note">
                    Source video files and thumbnails are excluded from Generated Data calculation.
                  </Alert>
                </SpaceBetween>
              </ExpandableSection>
              <ExpandableSection
                headerText="Storage Cost Disclaimer"
                variant="container"
                defaultExpanded={false}
              >
                <Alert type="info" header="Reference Only">
                  <SpaceBetween size="xs">
                    <div>
                      Storage cost is calculated based on <strong>Generated Data</strong> only (excluding source videos)
                      using the <strong>S3 Standard</strong> storage rate (approx. $0.023 per GB/month).
                    </div>
                    <ul style={{ marginTop: '0.5rem', marginBottom: '0.5rem', paddingLeft: '1.5rem' }}>
                      <li><strong>Source Video Size:</strong> Original uploaded video files</li>
                      <li><strong>Generated Data:</strong> Frames, embeddings, analysis outputs, and metadata</li>
                    </ul>
                    <a href="https://aws.amazon.com/s3/pricing/" target="_blank" rel="noopener noreferrer">
                      AWS S3 Pricing
                    </a>
                  </SpaceBetween>
                </Alert>
              </ExpandableSection>
              <Table
                columnDefinitions={[
                  { id: "workflow", header: "Workflow", cell: item => item.workflow },
                  { id: "videos", header: "Videos", cell: item => item.videos },
                  { id: "sourceVideoSize", header: "Source Video Size", cell: item => formatBytes(item.sourceVideoSize) },
                  { id: "dataSize", header: "Generated Data Size", cell: item => formatBytes(item.dataSize) },
                  { id: "sourceVideoStorageCost", header: "Source Video Storage ($)", cell: item => item.sourceVideoStorageCost.toFixed(6) },
                  { id: "generatedDataStorageCost", header: "Generated Data Storage ($)", cell: item => item.generatedDataStorageCost.toFixed(6) },
                  { id: "totalCost", header: "Total Storage Cost ($)", cell: item => item.totalCost.toFixed(6) },
                ]}
                items={tableData}
                loadingText="Loading data"
                empty={
                  <Box textAlign="center" color="inherit">
                    <b>No data available</b>
                  </Box>
                }
              />
            </SpaceBetween>
          </Container>

          <ColumnLayout columns={2}>
            <Container header={<Header variant="h3">Storage Cost Breakdown</Header>}>
              <BarChart
                series={[
                  {
                    title: "Source Video Storage",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.sourceVideoStorageCost })),
                  },
                  {
                    title: "Generated Data Storage",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.generatedDataStorageCost })),
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

            <Container header={<Header variant="h3">Data Volume</Header>}>
              <BarChart
                series={[
                  {
                    title: "Source Video",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.sourceVideoSize / (1024 * 1024 * 1024) })),
                  },
                  {
                    title: "Generated Data",
                    type: "bar",
                    data: tableData.map(item => ({ x: item.workflow, y: item.dataSize / (1024 * 1024 * 1024) })),
                  },
                ]}
                xDomain={tableData.map(item => item.workflow)}
                yDomain={[0, Math.max(...tableData.map(d => (d.sourceVideoSize + d.dataSize) / (1024 * 1024 * 1024))) * 1.2]}
                xTitle="Workflow"
                yTitle="Size (GB)"
                height={300}
                stackedBars
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
