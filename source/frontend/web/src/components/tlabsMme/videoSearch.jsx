import React, {createRef} from 'react';
import './videoSearch.css'
import { Button, Link, FileInput, Alert, Spinner, Icon, Modal, Box, SpaceBetween, Badge, SegmentedControl, Tabs, Container, ButtonDropdown, Checkbox } from '@cloudscape-design/components';
import { FetchPost } from "../../resources/data-provider";
import DefaultThumbnail from '../../static/default_thumbnail.png';
import { getCurrentUser } from 'aws-amplify/auth';
import sample_images from '../../resources/sample-images.json'
import VideoUpload from './videoUpload';
import VideoPlayer from './videoPlayer';
import {DecimalToTimestamp} from "../../resources/utility"
import Diagram from "../../static/tlabs-mme-diagram.png"
import Architecture from "../../static/tlabs-mme-architecture.png"
import BroomIcon from "../../static/broom_button_icon.svg"


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
            pageSize: 50,
            mmScoreThreshold: 1.52,
            textScoreThreshold: 1.003,
            videoActiveTabId: "mmembed",
            selectedClip: null,
            uploadedFile: [],

            inputBytes: null,
            showDocModal: false,

            showDeleteConfirmModal: false,
            showFrame: [],
            showSampleImages: false,
            showSearchVideoModal: false,

            selectedModelId: "marengo30", // marengo27

            textScoreExpanded: false,
            imageScoreExpanded: false,
            showUploadModal: false,
            selectedEmbeddingOptions: ["visual"] // Default for marengo30
        };

        this.showMoreNumber = 8;
        this.searchTimer = null;
        this.searchOptions = [
                { text: "Keyword search", id: "text" },
                { text: "Semantic search", id: "text_embedding" },
                { text: "Multimodal search", id: "mm_embedding"},
            ];
        
        // Embedding options for different models
        this.embeddingOptionsMarengo30 = [
            { label: "Visual", value: "visual", id: "visual" },
            { label: "Audio", value: "audio", id: "audio" },
            { label: "Transcription", value: "transcription", id: "transcription" }
        ];
        
        this.embeddingOptionsMarengo27 = [
            { label: "Visual-Text", value: "visual-text", id: "visual-text" },
            { label: "Visual-Image", value: "visual-image", id: "visual-image" },
            { label: "Audio", value: "audio", id: "audio" }
        ];
    }

    handleVideoClick = (taskId, autoPlay) => {
        //console.log(autoPlay);
        this.props.onThumbnailClick(taskId, autoPlay);
    }

    handleSearchVideoClick = (clip) => {
        this.setState({
            selectedClip: null
        }, ()=> {
            this.setState({
                showSearchVideoModal: true,
                selectedClip: clip
            });
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
          this.setState({status: "loading", embedSearchItems: [], items: [], selectedClip: null});
          if (!this.state.filterText && !this.state.inputBytes)
            this.searchAll();
          else {
            this.searchEmbedding();
          }

    }
    searchAll() {
          const { username } = getCurrentUser().then((username)=>{
            FetchPost("/tlabs/embedding/search-task",{
                "SearchText": this.state.filterText,
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "TaskType": this.state.selectedModelId
            }, "TLabsService").then((data) => {
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (resp !== null) {
                            var items = resp;
                            //console.log(items);
                            this.setState(
                                {
                                    items: items === null?[]:items,
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
    searchEmbedding() {
          const { username } = getCurrentUser().then((username)=>{
            const embeddingOptions = this.state.selectedEmbeddingOptions.length > 0 
                ? this.state.selectedEmbeddingOptions
                : [];
            
            FetchPost("/tlabs/embedding/search-task-vector", {
                "SearchText": this.state.filterText,
                "Source": "",
                "InputType": this.state.inputBytes?"image":"text", // image, video, audio
                "InputBytes": this.state.inputBytes === null? null: this.state.inputBytes.split("base64,")[1],
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "TaskType": this.state.selectedModelId,
                "EmbeddingOptions": embeddingOptions
            }, "TLabsService").then((data) => {
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (resp !== null) {
                            var items = resp;
                            //console.log(items);
                            this.setState(
                                {
                                    items: [],
                                    embedSearchItems: items === null?[]:items,
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
        FetchPost("/tlabs/embedding/delete-task", {
            "TaskId": this.state.selectedItemId
          }, "TLabsService").then((data) => {
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

    getEmbeddingOptionsForModel = () => {
        return this.state.selectedModelId === "marengo30" 
            ? this.embeddingOptionsMarengo30 
            : this.embeddingOptionsMarengo27;
    }

    toggleEmbeddingOption = (optionValue) => {
        const isSelected = this.state.selectedEmbeddingOptions.includes(optionValue);
        let newSelected;
        
        if (isSelected) {
            newSelected = this.state.selectedEmbeddingOptions.filter(v => v !== optionValue);
        } else {
            newSelected = [...this.state.selectedEmbeddingOptions, optionValue];
        }
        
        this.setState({ selectedEmbeddingOptions: newSelected });
    }

    getButtonDropdownItems = () => {
        const options = this.getEmbeddingOptionsForModel();
        return options.map(option => {
            const isChecked = this.state.selectedEmbeddingOptions.includes(option.value);
            return {
                id: option.value,
                text: `${isChecked ? '✓ ' : ''}${option.label}`,
                disabled: false
            };
        });
    }

    render() {
        return (
            <div className="tlabsvideosearch">
                {this.state.alert !== undefined && this.state.alert !== null && this.state.alert.length > 0?
                <Alert statusIconAriaLabel="Warning" type="warning">
                {this.state.alert}
                </Alert>:<div/>}
                    <div className='title'>TwelveLabs - Video Embedding
                        &nbsp;&nbsp;&nbsp;<Link onClick={()=>{this.setState({showDocModal: true})}}><Icon name="support"></Icon></Link>
                    </div>
                    <div className='model'>
                    <Tabs
                        selectedId={this.state.selectedModelId}
                        onChange={({ detail }) => {
                            const newModelId = detail.activeTabId;
                            // Set default embedding option based on model
                            const defaultOption = newModelId === "marengo30" ? ["visual"] : ["visual-image"];
                            this.setState({
                                selectedModelId: newModelId,
                                selectedEmbeddingOptions: defaultOption,
                                embedSearchItems: [],
                                filterText: "",
                                inputBytes: null
                            }, () => this.searchAll());
                        }}
                        tabs={[
                            { label: "Marengo 3.0", id: "marengo30" },
                            { label: "Marengo 2.7", id: "marengo27" },
                        ]}
                    />
                    </div>
                    <div className='globalaction'>
                        {this.props.readonlyMode !== true?
                        <div className='upload'><Button onClick={()=>this.setState({showUploadModal: true})} variant="primary">
                            <Icon name="upload" />&nbsp;
                            Upload a video
                        </Button></div>
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
                                placeholder="Search"
                                onChange={(e)=>this.setState({filterText:e.target.value})}
                                onKeyDown={(e)=>{if(e.key === "Enter")this.populateItems()}}
                                value={this.state.filterText}
                            />
                            }
                        </div>
                        <div className='clear'>
                            {(this.state.filterText || this.state.inputBytes) && <Link onClick={()=> {{this.setState({filterText: "", inputBytes: null, clipItems: []}, () => this.populateItems());}}}>
                                <Icon name="close" />
                            </Link>}
                        </div>
                        <div className='search'>
                            <Button variant='primary' onClick={()=>this.populateItems()}><Icon name="search" /></Button>&nbsp;
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
                        <div className='searchoptions'>
                            <ButtonDropdown
                                items={this.getButtonDropdownItems()}
                                onItemClick={({ detail }) => this.toggleEmbeddingOption(detail.id)}
                                expandableGroups
                            >
                                <span>
                                    Embedding Options
                                    {this.state.selectedEmbeddingOptions.length > 0 && (
                                        <> <Badge color="blue">{this.state.selectedEmbeddingOptions.length}</Badge></>
                                    )}
                                </span>
                            </ButtonDropdown>
                        </div>
                    </div>
                
                {this.state.status === "loading"?<Spinner/>:<div/>}
                {this.state.embedSearchItems?.length > 0 ? 
                <Button
                    onClick={()=> {{this.setState({filterText: "", inputBytes: null, clipItems: [], items:[]}, () => this.populateItems());}}}
                    >
                        <img className='cleanup' src={BroomIcon} alt="cleanup"></img>
                </Button>:
                <Button onClick={()=>{this.populateItems();}}><Icon name="refresh" /></Button>}
                <div>
                {this.state.embedSearchItems && this.state.embedSearchItems.map((l,i)=>{
                    return <div className="thumb" key={l.TaskId} onClick={({ detail }) => {this.handleSearchVideoClick(l);}}>
                        <VideoPlayer key={`${l.TaskId}_${l.StartSec}`} src={l.VideoUrl} startTime={l.StartSec} controls={false}/>
                        <div className="title">{l.TaskName}</div>
                        <div className="timestamp">{DecimalToTimestamp(l.StartSec)} - {DecimalToTimestamp(l.EndSec)} s</div>
                        <div className="status">{l.embeddingOption}[{l.EmbeddingOption}] Distance: {l.Distance.toFixed(5)}</div>
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
                            startTime={this.state.selectedClip.StartSec} 
                            endTime={this.state.selectedClip.EndSec} 
                            controls={true} 
                            autoPlay={true} 
                            className="videom"/>
                        <div className="timestamp">{DecimalToTimestamp(this.state.selectedClip.StartSec)} - {DecimalToTimestamp(this.state.selectedClip.EndSec)} s</div>
                        <div className="desc">{this.state.selectedClip.EmbeddingOption}</div>
                        <div className="desc">Distance: {this.state.selectedClip.Distance}</div>
                    </div>
                    }
                </Modal>
                    
                {this.state.items?this.state.items.map((l,i)=>{
                    return  <div className="thumb" key={l.TaskId}>
                                {l.ThumbnailUrl === undefined || l.ThumbnailUrl === null? 
                                    <img key={crypto.randomUUID()} className='img' src={DefaultThumbnail} alt="Generating thumbnail" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                    :<img key={crypto.randomUUID()} className='img' src={l.ThumbnailUrl} alt={l.FileName} onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                
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
                             
                }): 
                this.state.items.length === 0 && this.state.status === null? <div className="noresult">No video found</div>
                :<div/>
                }
                <Modal
                    onDismiss={() => this.setState({showDocModal: false})}
                    visible={this.state.showDocModal}
                    header={`About multimodal embedding workflow`}
                    size='large'
                >
                    <Tabs
                        tabs={[
                            {
                                label: "Multi-modal embedding video search",
                                id: "diagram",
                                content: <div>
                                    <img src={Diagram} max-width={"100%"}/>
                                </div>
                            },
                            {
                                label: "Architecture",
                                id: "architecture",
                                content: <div>
                                    <img src={Architecture} max-width={"100%"}/>
                                </div>
                            }
                        ]}
                        />
                </Modal>                    

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
                    <VideoUpload onSubmit={this.handleVideoUpload} onCancel={()=>this.setState({showUploadModal: false})} taskType={this.state.videoActiveTabId} selectedModelId={this.state.selectedModelId} />
                </Modal>
            </div>
        );
    }
}

export default VideoSearch;