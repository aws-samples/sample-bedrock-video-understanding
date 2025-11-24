import React, {createRef} from 'react';
import './videoSearch.css'
import { Button, Link, FileInput, Alert, Spinner, Icon, Modal, Box, SpaceBetween, Badge, ExpandableSection, Tabs, Container, Header } from '@cloudscape-design/components';
import { FetchPost } from "../../resources/data-provider";
import { refreshThumbnailUrls } from "../../resources/thumbnail-utils";
import DefaultThumbnail from '../../static/default_thumbnail.png';
import { getCurrentUser } from 'aws-amplify/auth';
import VideoUpload from './videoUpload';
import {DecimalToTimestamp} from "../../resources/utility"
import Diagram from "../../static/shot-based-diagram.png"
import FlowDiagram from "../../static/shot-based-flow.png"
import Architecture from "../../static/shot-based-architecture.png"
import StepFunctionWorkflow from "../../static/shot_graph.svg"
import BroomIcon from "../../static/broom_button_icon.svg"

class VideoSearch extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            filterText: "",
            items: [],
            clipItems: [],
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
            showUploadModal: false,
            showDocModal:false,
            uploadedFile: [],

            textScoreExpanded: false,
            imageScoreExpanded: false,
        };
        this.selectedClipRef = React.createRef();
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
        }, () => {
            if (this.selectedClipRef.current) {
                this.selectedClipRef.current.load(); // reloads <video> source
                this.selectedClipRef.current.play();
            }
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
        this.setState({status: "loading", items: [], clipItems: []});

        if((this.state.filterText !== null && this.state.filterText.length > 0) || this.state.inputBytes !== null) this.searchVector();
        else this.searchAll();

    }

    searchAll() {
          const { username } = getCurrentUser().then((username)=>{
            FetchPost("/extraction/video/search-task",{
                "SearchText": this.state.filterText,
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "TaskType": "clip"
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


      searchVector() {
          const { username } = getCurrentUser().then((username)=>{
            FetchPost("/extraction/video/search-vector",{
                "SearchText": this.state.filterText,
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "InputBytes": this.state.inputBytes?this.state.inputBytes.split("base64,")[1]:null,
                "InputType": this.state.inputBytes?"image":"text",
                "InputFormat": this.state.uploadedFile && this.state.uploadedFile.length > 0?this.state.uploadedFile[0].type.split("/")[1]:""
            }, "ExtrService").then((data) => {
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (resp !== null) {
                            var clipItems = resp;
                            //console.log(items);
                            this.setState(
                                {
                                    clipItems: clipItems === null?[]:clipItems,
                                    status: null,
                                    alert: null,
                                }
                            );
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
  
    handleImageChange = (files) => {
        const file = files[0];

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

    handleVideoUpload = () => {
        this.setState({showUploadModal: false, refreshSearchTaskId: Math.random().toString()});
        this.populateItems();
    }

    render() {
        return (
            <div className="clipvideosearch">
                {this.state.alert !== undefined && this.state.alert !== null && this.state.alert.length > 0?
                <Alert statusIconAriaLabel="Warning" type="warning">
                {this.state.alert}
                </Alert>:<div/>}
                    <div className='globalaction'>
                        <div className='title'>Shot-based video analysis
                            &nbsp;&nbsp;&nbsp;<Link onClick={()=>{this.setState({showDocModal: true})}}><Icon name="support"></Icon></Link>
                        </div>
                        {this.props.readonlyMode !== true?
                        <div className='upload'>
                            <Button onClick={()=>this.setState({showUploadModal: true})} variant='primary'>
                                <Icon name="upload" />&nbsp;
                                Upload a video
                            </Button>
                        </div>
                        :<div className='readonly-note'>Upload is currently disabled for this user</div>}
                        <div/>
                    </div>
                    <div className='searchinput'>
                        <div className='input'>
                            
                            {this.state.inputBytes !== null?
                                <div className='previewupload'>
                                    <img src={this.state.inputBytes}></img>
                                </div>
                            :<input
                                type="text"
                                className="input-text"
                                placeholder="Search video embedding"
                                onChange={(e)=>this.setState({filterText:e.target.value})}
                                onKeyDown={(e)=>{if(e.key === "Enter")this.populateItems()}}
                                value={this.state.filterText}
                            />
                            }
                        </div>
                        <div className='clear'>
                            {(this.state.filterText || this.state.inputBytes) &&
                            <Link onClick={()=> {{this.setState({filterText: "", inputBytes: null, clipItems: [], items:[]}, () => this.populateItems());}}}>
                                <Icon name="close" />
                            </Link>}
                        </div>
                        <div className='search'>
                            <SpaceBetween direction="horizontal" size="xs">
                                <Button variant='primary' onClick={()=>this.populateItems()}><Icon name="search" /></Button>
                            </SpaceBetween>
                        </div>
                        <div className='upload'>
                            <FileInput accept='.png,.jpeg,.gif,.webp'
                                onChange={({detail})=>{
                                    this.setState({uploadedFile: detail.value});
                                    this.handleImageChange(detail.value);
                                }}
                                value={this.state.uploadedFile}
                            >
                                Image Search
                            </FileInput>
                        </div>
                    </div>
                
                {this.state.status === "loading"?<Spinner/>:<div/>}
                {this.state.clipItems?.length > 0 ? 
                <Button
                    onClick={()=> {{this.setState({filterText: "", inputBytes: null, clipItems: [], items:[]}, () => this.populateItems());}}}
                    >
                        <img className='cleanup' src={BroomIcon} alt="cleanup"></img>
                </Button>:
                <Button onClick={()=>{this.populateItems();}}><Icon name="refresh" /></Button>}
                <div>
                {this.state.clipItems && this.state.clipItems?.map((l,i)=>{
                    return <div className="thumb" key={l.TaskId} onClick={({ detail }) => {this.handleSearchVideoClick(l);}}>
                        <div className="duration"><Badge color='blue'>{DecimalToTimestamp(l.StartSec)} - {DecimalToTimestamp(l.EndSec)}</Badge></div>
                        <div className="distance">{l.embeddingOption} Distance: {l.Distance && l.Distance.toFixed(5)}</div>
                        <video preload="auto">
                            <source src={l.VideoUrl} />
                        </video>
                        <div className="title">{l.TaskName}</div>
                    </div>
                })}
                <Modal
                    onDismiss={() => this.setState({showSearchVideoModal: false})}
                    visible={this.state.showSearchVideoModal}
                    header={`Video clip`}
                    size='x-large'
                >
                    {this.state.selectedClip &&
                    <div className='videomdoal'>
                        <div className="left">
                            <video controls ref={this.selectedClipRef} muted preload="auto">
                                <source src={this.state.selectedClip?.VideoUrl} />
                            </video>
                        </div>
                        <div className='right'>
                            <div className="timestamp">{DecimalToTimestamp(this.state.selectedClip.StartSec)} - {DecimalToTimestamp(this.state.selectedClip.EndSec)} s</div>
                            <br/>
                            <div className="desc">Distance: {this.state.selectedClip.Distance.toFixed(5)}</div>
                            <div className="desc">Embedding Type: {this.state.selectedClip.EmbeddingOption}</div>
                            <br/>
                            {this.state.selectedClip?.ShotOutputs.map((item, index)=>{
                                return <div className='output'>
                                    <div className='title'>{item.name} [{item.model_id}]</div>
                                    {item.value}
                                </div>
                            })}
                        </div>
                    </div>
                    }
                </Modal>
                <Modal
                    onDismiss={() => this.setState({showDocModal: false})}
                    visible={this.state.showDocModal}
                    header={`About shot-based workflow`}
                    size='x-large'
                >
                    <div className='clipdoc'>
                    <Tabs
                        tabs={[
                            {
                                label: "What is video shot",
                                id: "diagram",
                                content: 
                                    <div>
                                        <div className='center'>
                                            A video shot is a single, uninterrupted series of frames recorded from the moment a camera starts until it stops. It is the most basic building block of video and filmmaking. 
                                            <br/><br/>
                                            <img src={Diagram}/>
                                            <br/><br/>
                                            Applying video understanding and multimodal embeddings at the shot level is well-suited for video search use cases, especially for professionally edited content such as TV shows, films, documentaries, news, sports, advertising creatives, educational training videos, and more.
                                        </div>
                                    </div>
                            },
                            {
                                label: "Shot based video analysis",
                                id: "flow",
                                content: 
                                    <div className='center'>
                                         <img src={FlowDiagram}/>
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
                {this.state.clipItems?.length === 0 && this.state.items?.map((l,i)=>{
                    return  <div className="thumb" key={l.TaskId}>
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
                            </div>
                    }) 
                }
                {(this.state.clipItems === null || this.state.clipItems.length === 0) && this.state.items?.length === 0 && <div className="noresult">No video found</div>}


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