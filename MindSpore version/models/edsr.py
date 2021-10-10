import mindspore
from models import common
from option import opt

import mindspore.nn as nn
import mindspore.ops as ops
import mindspore.ops.operations as P
from mindspore import Tensor

class EDSR(nn.Cell):
    def __init__(self, args):
        super(EDSR, self).__init__()

        self.n_colors = args.n_colors
        n_resblocks = args.n_resblocks
        self.n_feats = args.n_feats
        self.kernel_size = 3
        scale = args.scale[0]
        act = nn.ReLU()
        self.rgb_range = args.rgb_range

        # self.head = nn.Conv2d(in_channels=args.n_colors, out_channels=self.n_feats, kernel_size=self.kernel_size, pad_mode='pad', padding=self.kernel_size // 2, has_bias=True)
        self.head = common.conv(args.n_colors, self.n_feats, self.kernel_size, padding=self.kernel_size//2)

        m_body = [
            common.ResidualBlock(
                self.n_feats, self.kernel_size, act=act, res_scale=args.res_scale
            ) for _ in range(n_resblocks)
        ]
        # self.body = nn.SequentialCell(m_body)
        self.body = m_body
        # self.body_conv = nn.Conv2d(in_channels=self.n_feats, out_channels=self.n_feats, kernel_size=self.kernel_size, pad_mode='pad', padding=self.kernel_size // 2, has_bias=True)
        self.body_conv = common.conv(self.n_feats, self.n_feats, self.kernel_size, padding=self.kernel_size//2)

        self.upsampler = common.Upsampler(scale, self.n_feats)
        # self.tail_conv = nn.Conv2d(in_channels=self.n_feats, out_channels=args.n_colors, kernel_size=self.kernel_size, pad_mode='pad', padding=self.kernel_size // 2, has_bias=True)
        self.tail_conv = common.conv(self.n_feats, args.n_colors, self.kernel_size, padding=self.kernel_size//2)

    # def construct(self, x, width_mult=1.0):
    def construct(self, x, width_mult):
        if opt.obs:
            feature_width = 1.0
            if width_mult != 1:
                feature_width = int(self.n_feats * 0.25)
        else:
            width_mult = width_mult.asnumpy().item()
            feature_width = int(self.n_feats * width_mult)
        conv2d = ops.Conv2D(out_channel=feature_width, kernel_size=self.kernel_size, mode=1, pad_mode='pad',
                            pad=self.kernel_size // 2)
        biasadd = ops.BiasAdd()

        if not opt.obs:
            x = common.MeanShift(x, self.rgb_range)
        weight = self.head.weight.clone()[:feature_width, :self.n_colors, :, :]
        bias = self.head.bias.clone()[:feature_width]
        x = conv2d(x, weight)
        x = biasadd(x, bias)

        residual = x
        for block in self.body:
            residual = block(residual, width_mult)
        weight = self.body_conv.weight[:feature_width, :feature_width, :, :]
        bias = self.body_conv.bias[:feature_width]
        residual = conv2d(residual, weight)
        residual = biasadd(residual, bias)
        residual += x

        x = self.upsampler(residual, width_mult)
        weight = self.tail_conv.weight[:self.n_colors, :feature_width, :, :]
        bias = self.tail_conv.bias[:self.n_colors]
        conv2d = ops.Conv2D(out_channel=self.n_colors, kernel_size=self.kernel_size, mode=1, pad_mode='pad', pad=self.kernel_size//2)
        x = conv2d(x, weight)
        x = biasadd(x, bias)
        if not opt.obs:
            x = common.MeanShift(x, self.rgb_range, sign=1)

        return x