import React, {createRef} from 'react';
import './videoSearch.css'
import { Button, Link, Cards, Alert, Spinner, Icon, Modal, Box, SpaceBetween, Badge, ExpandableSection, Tabs, Container } from '@cloudscape-design/components';
import { FetchPost } from "../../resources/data-provider";
import { refreshThumbnailUrls } from "../../resources/thumbnail-utils";
import DefaultThumbnail from '../../static/default_thumbnail.png';
import { getCurrentUser } from 'aws-amplify/auth';
import sample_images from '../../resources/sample-images.json'
import VideoUpload from './videoUpload';
import VideoPlayer from './videoPlayer';
import {DecimalToTimestamp} from "../../resources/utility"
import Diagram from "../../static/frame-based-diagram.png"
import Architecture from "../../static/frame-based-architecture.png"
import StepFunctionWorkflow from "../../static/frame_graph.svg"

class VideoSearch extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            filterText: "",
            uploadFile: [],
            items: [],
            embedSearchItems: [],
            selectedItemId: null,
            pageSize: 8,
            mmScoreThreshold: 1.52,
            textScoreThreshold: 1.003,
            selectedClip: null,

            inputBytes: null,

            showDeleteConfirmModal: false,
            showFrame: [],
            showSampleImages: false,
            showSearchVideoModal: false,
            showDocModal: false,

            textScoreExpanded: false,
            imageScoreExpanded: false,
            showUploadModal: false
        };

        this.showMoreNumber = 8;
        this.searchTimer = null;
        this.searchOptions = process.env.REACT_APP_VECTOR_SEARCH === "enable"?
            [
                { text: "Keyword search", id: "text" },
                { text: "Semantic search", id: "text_embedding" },
                { text: "Multimodal search", id: "mm_embedding"},
            ]: 
            [{ text: "Video name", id: "video_name" }];
    }

    handleVideoClick = (taskId, autoPlay) => {
        //console.log(autoPlay);
        this.props.onThumbnailClick(taskId, autoPlay);
    }

    handleSearchVideoClick = (clip) => {
        this.setState({
            showSearchVideoModal: true,
            selectedClip: clip
        });

    }

    async componentDidMount() {
        if (this.state.items === null || this.state.items.length === 0)  {
          this.populateItems();    
        }
    }

    componentDidUpdate(prevProps) {
        if (prevProps.refreshSearchTaskId !== this.props.refreshSearchTaskId) {
            this.populateItems();    
        }
      }

    populateItems() {
        this.setState({status: "loading", embedSearchItems: [], items: []});
        this.searchAll();

    }
    searchAll() {
          const { username } = getCurrentUser().then((username)=>{
            FetchPost("/extraction/video/search-task",{
                "SearchText": this.state.filterText,
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "TaskType": "frame"
            }, "ExtrService").then((data) => {
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (resp !== null) {
                            refreshThumbnailUrls(resp, "ExtrService").then(itemsWithUrls => {
                                this.setState(
                                    {
                                        items: itemsWithUrls === null?[]:itemsWithUrls,
                                        status: null,
                                        alert: null,
                                    }
                                );
                            });
                        }
                    }
                })
                .catch((err) => {
                    this.setState( {status: null, alert: err.message});
                });              
          }

          )
      }

      handleDelete = e => {
        if (this.state.selectedItemId === null) return;

        this.setState({status: "loading"});
        FetchPost("/extraction/video/delete-task", {
            "TaskId": this.state.selectedItemId
          }, "ExtrService").then((data) => {
                  var resp = data.body;
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body, showDeleteConfirmModal: false});
                  }
                  else {
                      if (resp !== null) {
                          //console.log(resp);
                          this.setState(
                              {
                                  status: null,
                                  alert: null,
                                  items: this.state.items.filter(item => item.TaskId !== this.state.selectedItemId),
                                  selectedItemId: null,
                                  showDeleteConfirmModal: false
                              }
                          );
                      }
                  }
              })
              .catch((err) => {
                  this.setState( {status: null, alert: err.message, showDeleteConfirmModal: false});
              });  
      }
  
    handleImageChange = (event) => {
        const file = event.target.files[0];
    
        if (file) {
          const reader = new FileReader();
    
          //const base64Str = reader.result;
          reader.onloadend = () => {
            this.setState({
              inputBytes: reader.result,
            });
          };
    
          reader.readAsDataURL(file);
        }
      };

    handleSampleSelect = e => {
        this.setState({
            showSampleImages: false,
            inputBytes: e.detail.selectedItems[0].image_bytes,
            status: null
        });

    }
    handleVideoUpload = () => {
        this.setState({showUploadModal: false, refreshSearchTaskId: Math.random().toString()});
        this.populateItems();
    }

    render() {
        return (
            <div className="framevideosearch">
                {this.state.alert !== undefined && this.state.alert !== null && this.state.alert.length > 0?
                <Alert statusIconAriaLabel="Warning" type="warning">
                {this.state.alert}
                </Alert>:<div/>}
                    <div className='globalaction'>
                        <div className='title'>Frame sampling-based video analysis 
                            &nbsp;&nbsp;&nbsp;<Link onClick={()=>{this.setState({showDocModal: true})}}><Icon name="support"></Icon></Link>
                        </div>
                        {this.props.readonlyMode !== true?
                        <div className='upload'><Button onClick={()=>this.setState({showUploadModal: true})} variant="primary">
                            <Icon name="upload" />&nbsp;
                            Upload a video
                        </Button></div>
                        :<div className='readonly-note'>Upload is currently disabled for this user</div>}
                        <div/>
                    </div>
                     <div className='searchinput'>
                        <div>
                            <input
                                type="text"
                                className="input-text"
                                placeholder="Search by video title"
                                onChange={(e)=>this.setState({filterText:e.target.value})}
                                onKeyDown={(e)=>{if(e.key === "Enter")this.populateItems()}}
                                value={this.state.filterText}
                                />
                            <div className='clean'>
                                <Link onClick={()=> {this.setState({filterText: "", inputBytes: null, embedSearchItems: null}, () => this.populateItems());}}>
                                    <Icon name="close" />
                                </Link>
                            </div>
                            <div className='search'>
                                <Button variant='primary' onClick={()=>this.populateItems()}><Icon name="search" /></Button>
                                &nbsp;<Button onClick={()=>{this.populateItems();}}><Icon name="refresh" /></Button>
                            </div>
                        </div>
                    </div>
                
                {this.state.status === "loading"?<Spinner/>:<div/>}
                <div>
                {this.state.embedSearchItems && this.state.embedSearchItems.map((l,i)=>{
                    return <div className="thumbnail" key={l.TaskId}>
                        <VideoPlayer src={l.VideoUrl} startTime={l.startSec} controls={false}/>
                        <div className="title" onClick={({ detail }) => {this.handleSearchVideoClick(l);}}>{l.TaskName}</div>
                        <div className="timestamp">{DecimalToTimestamp(l.startSec)} - {DecimalToTimestamp(l.endSec)} s</div>
                        <div className="status">{l.embeddingOption} (Score: {l.score.toFixed(5)})</div>
                    </div>
                })}
                <Modal
                    onDismiss={() => this.setState({showSearchVideoModal: false})}
                    visible={this.state.showSearchVideoModal}
                    header={`Video clip`}
                    size='large'
                >
                    {this.state.selectedClip &&
                    <div className='videomdoal'>
                        <VideoPlayer 
                            src={this.state.selectedClip.VideoUrl} 
                            startTime={this.state.selectedClip.startSec} 
                            endTime={this.state.selectedClip.endSec} 
                            controls={true} 
                            autoPlay={true} 
                            className="videom"/>
                        <div className="timestamp">{DecimalToTimestamp(this.state.selectedClip.startSec)} - {DecimalToTimestamp(this.state.selectedClip.endSec)} s</div>
                        <div className="desc">{this.state.selectedClip.embeddingOption}</div>
                    </div>
                    }
                </Modal>

                <Modal
                    onDismiss={() => this.setState({showDocModal: false})}
                    visible={this.state.showDocModal}
                    header={`About frame-based workflow`}
                    size='larger'
                >
                    <div className='shotdoc'>
                        <Tabs
                            tabs={[
                                {
                                    label: "Frame sampling based video analysis",
                                    id: "diagram",
                                    content: <div className='center'>
                                        <img src={Diagram}/>
                                    </div>
                                },
                                {
                                    label: "Architecture",
                                    id: "architecture",
                                    content: <div className='center'><img width={"100%"} src={Architecture}></img></div>
                                },
                                {
                                    label: "Step Function Workflow",
                                    id: "stepfunction",
                                    content: <div className='center'><img width={"100%"} src={StepFunctionWorkflow}></img></div>
                                },
                            ]}
                            />
                        </div>
                </Modal>
                    
                {this.state.items !== undefined && this.state.items !== null && this.state.items.length > 0?this.state.items.map((l,i)=>{
                    return  <div className="thumbnail" key={l.TaskId}>
                                {l.ThumbnailUrl === undefined || l.ThumbnailUrl === null? 
                                    <img className='img' src={DefaultThumbnail} alt="Generating thumbnail" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                    :<img className='img' src={l.ThumbnailUrl} alt={l.FileName} onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                
                                }
                                <div className="title" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}>{l.TaskName}</div>
                                <div className='status'>{l.Status}</div>
                                <div className="timestamp">{l.RequestBy} - {new Date(l.RequestTs).toLocaleString()}</div>
                                {this.props.readonlyMode? <div/>:
                                <div className='action'onClick={(e) => {
                                    this.setState({
                                        showDeleteConfirmModal: true,
                                        selectedItemId: l.TaskId
                                    })}}>
                                <Icon name="remove" visible={!this.props.readonlyMode} /></div>}
                                {l.Frames !== undefined && l.Frames !== null && l.Frames.length > 0?
                                <div>
                                    {
                                        this.state.showFrame.includes(l.TaskId)?
                                        <div>
                                            <Button iconName="treeview-collapse" variant="icon" onClick={()=>this.setState({showFrame: []})}></Button>
                                            {l.Frames.length} frames
                                            <div class="frames">
                                                <div className='close'>
                                                    <Button iconName="close" variant="icon" onClick={()=>this.setState({showFrame: []})}></Button>
                                                </div>                                            
                                                {l.Frames.map((item,idx)=> {
                                                    return <div className='box'>

                                                            <img src={item.image_uri}></img>
                                                            <div className="item">
                                                                <div className="key">Timestamp:</div>
                                                                {item.timestamp}
                                                            </div>
                                                            <div className="item">
                                                                <div className="key">Score:</div>
                                                                {item.score}
                                                            </div>
                                                            <div className="item">
                                                                <div className="key">Embedding Tex:</div>
                                                                {item.embedding_text}
                                                            </div>
                                                        </div>
                                                })}    
                                            </div>                                    
                                        </div>
                                        :<div>
                                            <Button iconName="treeview-expand" variant="icon" onClick={()=>this.setState({showFrame: [l.TaskId]})}></Button>
                                            {l.Frames.length} frames
                                        </div>
                                    }
                                </div>
                                :<div/>}
                            </div>
                             
                }): 
                this.state.items.length === 0 && this.state.status === null? <div className="noresult">No video found</div>
                :<div/>
                }

                <Modal
                    onDismiss={() => this.setState({showDeleteConfirmModal: false})}
                    visible={this.state.showDeleteConfirmModal}
                    header="Delete the video"
                    size='medium'
                    footer={
                        <Box float="right">
                          <SpaceBetween direction="horizontal" size="xs">
                            <Button variant="link" onClick={() => this.setState({showDeleteConfirmModal: false})}>Cancel</Button>
                            <Button variant="primary" loading={this.state.status === "loading"} onClick={this.handleDelete}>Yes</Button>
                          </SpaceBetween>
                        </Box>
                      }
                >
                    Are you sure you want to delete the video and analysis reports?
                </Modal>
                </div>
                <div className="showmore">
                    <Button 
                        loading={this.state.status === "loading"}
                        onClick={() => {
                            this.setState({pageSize: this.state.pageSize + this.showMoreNumber});
                            this.searchTimer = setTimeout(() => {
                                this.populateItems();
                              }, 500); 
                    }}>Show more</Button>
                </div>
                <Modal
                    onDismiss={() => this.setState({showUploadModal: false})}
                    visible={this.state.showUploadModal}
                    size='max'
                >
                    <VideoUpload onSubmit={this.handleVideoUpload} onCancel={()=>this.setState({showUploadModal: false})} />
                </Modal>
            </div>
        );
    }
}

export default VideoSearch;