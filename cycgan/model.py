import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np


def pixel_shuffle(x, size=2):
    
    b, c, t = x.size()

    new_c, new_t = c // size, t * size
    
    return x.view(b, new_c, new_t) 



class Upsample1DBlock(nn.Module):
    
    def __init__(self, dim_in, dim_out, kernel_size, stride, padding):
        
        super().__init__()

        self.conv = nn.Conv1d(dim_in, dim_out, kernel_size = kernel_size, stride = stride, padding = padding, bias = False)
        self.inst_norm = nn.InstanceNorm1d(dim_out //2, affine = True)
        self.glu = nn.GLU(1)
        
    def forward(self, x):
        
        out = self.conv(x)
        out = pixel_shuffle(out)
        out = self.inst_norm(out)
        out = self.glu(out)
        
        return out 


class Downsample1DBlock(nn.Module):

    def __init__(self, dim_in, dim_out, kernel_size, stride, padding):
        
        super().__init__()

        self.conv1 = nn.Conv1d(dim_in, dim_out, kernel_size = kernel_size, stride = stride, padding = padding, bias = False)
        self.inst_norm = nn.InstanceNorm1d(dim_out, affine = True)
        self.glu = nn.GLU(1)
    def forward(self, x):
        out = self.conv1(x)
        out = self.inst_norm(out)
        out = self.glu(out)

        return out

class ResidualBlock(nn.Module):
    """Residual Block with instance normalization."""
    def __init__(self, dim_in, dim_out):
        super(ResidualBlock, self).__init__()
        self.conv = nn.Conv1d(dim_in, dim_out, kernel_size=3, stride=1, padding=1, bias=False)
        self.inst_norm = nn.InstanceNorm1d(dim_out, affine = True)
        self.glu = nn.GLU(1)

    def forward(self, x):
        x_ = self.conv(x)
        x_ = self.inst_norm(x_)
        x_ = self.glu(x_)

        return x_


class Generator(nn.Module):

    def __init__(self, input_dim = 36, conv_dim = 64, num_speakers = 4, repeat_num = 6):
        super().__init__()
        
        layers = []

        layers.append(nn.Conv1d(input_dim, 256, kernel_size = 15, stride = 1, padding = 7, bias = False))
        layers.append(nn.GLU(1))

        # Downsample

        layers.append(Downsample1DBlock(128, 256, 5, 2, 1))
        layers.append(Downsample1DBlock(128, 512, 5, 2, 2))

        # Bottleneck layers

        for _ in range(repeat_num):
            layers.append( ResidualBlock(256, 512))
        
        # Upsample
        
        layers.append(Upsample1DBlock(256, 512, 5, 1, 2))
        layers.append(Upsample1DBlock(128, 256, 5, 1, 2))
        
        layers.append(nn.Conv1d(64, input_dim, kernel_size = 15, stride = 1, padding = 7, bias = False  ))
        
        self.main = nn.Sequential(*layers)
    def forward(self, x):
        
        out = x
        out = self.main(out)
        return out



class Discriminator(nn.Module):
    def __init__(self, input_size=(36, 256), conv_dim=128, repeat_num=3):
        super(Discriminator, self).__init__()
        layers = []
        layers.append(nn.Conv2d(1, 2 *conv_dim, kernel_size=2, stride=[1,2], padding=1))
        layers.append(nn.GLU(dim = 1))

        curr_dim = conv_dim
        for i in range(0, repeat_num):
            layers.append(nn.Conv2d(curr_dim , curr_dim*4, kernel_size=3, stride=2, padding=1))
            layers.append(nn.InstanceNorm2d(curr_dim *4, affine = True))
            layers.append(nn.GLU(dim=1))
            curr_dim = curr_dim * 2

        self.main = nn.Sequential(*layers)
        self.out_linear = nn.Linear(curr_dim, 128)
        
    def forward(self, x):
        x = x.unsqueeze(1) # b 1 36 256
        h = self.main(x) # b 1024 1 8
        out_src = self.out_linear(h.permute(0,2,3,1)).permute(0,3,1,2)
        #out_src = self.conv_dis(h)
        out_src = torch.sigmoid(out_src)
        #out_cls_spks = self.conv_clf_spks(h)
        return out_src #out_cls_spks.view(out_cls_spks.size(0), out_cls_spks.size(1))
        
        
