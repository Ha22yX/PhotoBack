/**
 * 视频处理器 - 管理视频缩略图和播放
 */
(function() {
    'use strict';
    
    // 调试模式设置
    var DEBUG_MODE = false;
    
    // 存储已处理过的媒体项
    var processedMediaItems = new Set();
    
    // 初始化函数
    function initVideoHandler() {
        console.log('视频处理器初始化');
        
        // 处理媒体数据
        processMediaItems();
        
        // 添加事件监听器
        addEventListeners();
    }
    
    // 处理所有媒体项目
    function processMediaItems() {
        var items = document.querySelectorAll('.photo-item');
        if (!items.length) return;
        
        console.log(`找到 ${items.length} 个媒体项`);
        
        items.forEach(function(item) {
            var index = parseInt(item.dataset.index || '0');
            
            // 检查是否已处理过
            if (processedMediaItems.has(index)) {
                return;
            }
            
            // 标记为已处理
            processedMediaItems.add(index);
            
            var imgElement = item.querySelector('img');
            var videoElement = item.querySelector('video');
            
            // 处理视频元素
            if (imgElement && imgElement.dataset.videoSrc) {
                var mediaId = imgElement.dataset.mediaId || '';
                var thumbnailSrc = imgElement.src;
                var videoSrc = imgElement.dataset.videoSrc;
                
                if (DEBUG_MODE) {
                    console.log(`处理视频[${index}] ID:${mediaId}, 缩略图:${thumbnailSrc}, 原视频:${videoSrc}`);
                }
                
                // 预加载缩略图
                if (thumbnailSrc) {
                    var preloadImg = new Image();
                    preloadImg.src = thumbnailSrc;
                }
            }
        });
    }
    
    // 安全地停止和清理视频元素
    function safelyCleanupVideo(videoElement) {
        if (!videoElement) return;
        
        try {
            // 暂停视频
            if (typeof videoElement.pause === 'function') {
                videoElement.pause();
            }
            
            // 完全移除错误处理程序（不再恢复）
            videoElement.onerror = null;
            
            // 记录原始src以便调试
            var originalSrc = videoElement.getAttribute('src');
            if (DEBUG_MODE && originalSrc) {
                console.log('正在清理视频元素，原始src:', originalSrc);
            }
            
            // 使用空白1x1像素透明视频替代直接清空src
            // 这比移除src属性更安全，避免触发空src错误
            videoElement.src = 'data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAA7RtZGF0AAACrAYF//+o3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE0OCByMjYwMSBhNGU0MDBjIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxOCAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTYgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEgc2NlbmVjdXQ9NDAgaW50cmFfcmVmcmVzaD0wIHJjX2xvb2thaGVhZD00MCByYz1jcmYgbWJ0cmVlPTEgY3JmPTIzLjAgcWNvbXA9MC42MCBxcG1pbj0wIHFwbWF4PTY5IHFwc3RlcD00IGlwX3JhdGlvPTEuNDAgYXE9MToxLjAwAIAAAAAwZYiEAD//8m+P5OXfBeLGOfKE3xQNoB9sYLk4RiEQlCu0F0/xGIBE9UIghfQj6LAQfjHz/AQc/wEDr/8BC///8BC///8AAAADgAAAYJlgEHupyyQAAAgAARVIgIgHL5EPb5QPr5QPb5QAAQASAABAHgAAAgMDaYNn8G/wGPYn/AAAAAM2o3VkdUQA';
            
            // 重置视频
            videoElement.currentTime = 0;
            videoElement.load();
            
            // 移除可能添加的播放按钮
            var playButton = document.querySelector('.video-play-button');
            if (playButton && playButton.parentNode) {
                playButton.parentNode.removeChild(playButton);
            }
        } catch (e) {
            console.error('清理视频元素时出错:', e);
        }
    }
    
    // 添加事件监听器
    function addEventListeners() {
        // 这里可以添加任何与视频相关的事件监听器
    }
    
    // 当DOM加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initVideoHandler);
    } else {
        initVideoHandler();
    }
    
    // 导出到全局作用域
    window.VideoHandler = {
        processMediaItems: processMediaItems,
        setDebugMode: function(mode) {
            DEBUG_MODE = !!mode;
        },
        safelyCleanupVideo: safelyCleanupVideo
    };
})(); 