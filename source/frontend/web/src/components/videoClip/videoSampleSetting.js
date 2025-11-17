import React, { Component } from 'react';
import { Container, FormField, Popover, Header, Toggle, ColumnLayout, Select, Input, Box, ExpandableSection, RadioGroup, Link } from '@cloudscape-design/components';
import VideoPromptConfig from './videoPromptConfig';
import ClipBasedConfig from '../../resources/clip-based-config.json'
import './videoSampleSetting.css'

class VideoSampleSetting extends Component {

    constructor(props) {
        super(props);
        this.state = {
            request: {},
            enableAudio: true,
            
            // shot level
            enableShotAnalysis: true,
            enableEmbedding: false,
            embedDim: ClipBasedConfig.default_embed_dimension,
            shotConfigs: null,

            startSec: null,
            lengthSec: null,
            useFixedLengthSec: null,
            minClipSec: null

        };
        this.shotPromptConfigRef = React.createRef();
    }   

  getRequest() {
    var shotConfigs = null, warns = [];
    if (this.shotPromptConfigRef?.current) {
        shotConfigs = this.shotPromptConfigRef.current.getConfigs();
    }

    if (shotConfigs?.warnings?.length > 0)
        return null;

    this.setState({shotConfigs: shotConfigs});

    return {
        "PreProcessSetting": {
            "StartSec": this.state.startSec,
            "LengthSec": this.state.lengthSec,
            "UseFixedLengthSec": this.state.useFixedLengthSec,
            "MinClipSec": this.state.minClipSec, //Default: 4, Min: 1, Max: 5.
        },
        "ExtractionSetting": {
            "Audio": {
                "Transcription": this.state.enableAudio
            },
            "Vision": {
                "Shot": {
                    "Embedding": {
                        "Enabled": this.state.enableEmbedding,
                        "ModelId": ClipBasedConfig.embed_model_id,
                        "Dimension": this.state.embedDim,
                    },
                    "Understanding": {
                        "Enabled": this.state.enableShotAnalysis,
                        "PromptConfigs": shotConfigs?.configs,
                    }
                }
            }
        }
    }
  }

  render() {
    return <div className='clipconfigsetting'>
              <Container header={<Header variant='h2'>Audio Setting</Header>}>
                  <Toggle
                      onChange={({ detail }) =>
                          this.setState({enableAudio: detail.checked})
                      }
                      checked={this.state.enableAudio}
                      >
                      Transcribe audio (with subtitle) using Amazon Transcribe
                  </Toggle>
              </Container>
              <br/>
              <Container header={
                <Header variant='h2'>
                    Analyze Shots
                </Header>
              }
                footer={
                        <ExpandableSection headerText="Shot Settings">
                            <Box variant="p" color="text-body-secondary" margin={{bottom: "s"}}>
                                By default, video segments are detected automatically using OpenCV scene detection. 
                                Use "Use fixed length" to create segments at fixed intervals instead.
                            </Box>
                            <ColumnLayout columns={2}>
                                <div>
                                    <div className='label'>Start (second)</div>
                                    <Input inputMode="numeric" type='number' value={this.state.startSec} onChange={({ detail }) => this.setState({startSec: parseFloat(detail.value)})}></Input>
                                </div>
                                <div>
                                    <div className='label'>Length (second)</div>
                                    <Input inputMode="numeric" type='number' value={this.state.lengthSec} onChange={({ detail }) => this.setState({lengthSec: parseFloat(detail.value)})}></Input>
                                </div>
                                <div>
                                    <div className='label'>Use fixed length (second)</div>
                                    <div className='desc'>1-60 (leave empty for OpenCV-based detection)</div>
                                    <Input inputMode="numeric" type='number' value={this.state.useFixedLengthSec} onChange={({ detail }) => this.setState({useFixedLengthSec: parseFloat(detail.value)})}></Input>
                                </div>
                                <div>
                                    <div className='label'>Minimum clip length (second)</div>
                                    <div className='desc'>1-5</div>
                                    <Input inputMode="numeric" type='number' value={this.state.minClipSec} onChange={({ detail }) => this.setState({minClipSec: parseFloat(detail.value)})}></Input>
                                </div>                                                                                                                               
                            </ColumnLayout>
                        </ExpandableSection>}
              >
                    <Box variant="p" color="text-body-secondary" margin={{bottom: "s"}}>
                        Generate embeddings using Amazon Nova Multimodal Embedding for flexible semantic search across video segments.
                    </Box>
                    <Toggle
                        onChange={({ detail }) =>
                            this.setState({enableEmbedding: detail.checked})
                        }
                        checked={this.state.enableEmbedding}
                        >
                        Enable shot embedding for vector search
                    </Toggle>
                    <br/>
                    <Box variant="p" color="text-body-secondary" margin={{top: "m", bottom: "s"}}>
                        Add prompts to analyze each video segment for classification or summary. Each prompt will be applied to every segment independently.
                    </Box>
                    <div>
                        <VideoPromptConfig 
                            selectedPromptId="shot_summary"
                            sampleConfigs={ClipBasedConfig.shot_prompts}
                            models={ClipBasedConfig.models}
                            ref={this.shotPromptConfigRef}
                            promptConfigs={this.state.shotConfigs}
                        />
                    </div>
              </Container>

    </div>

  };
};
export default VideoSampleSetting;