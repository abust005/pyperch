import numpy as np
import torch
from torch import nn
from skorch import NeuralNet
from pyperch.utils.decorators import add_to
from skorch.dataset import unpack_data
import copy


class RHCModule(nn.Module):
    def __init__(self, input_dim=20, output_dim=2, hidden_units=10, hidden_layers=1,
                 dropout_percent=0, lr=.1, activation=nn.ReLU(), output_activation=nn.Softmax(dim=-1)):
        super().__init__()
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.hidden_units = hidden_units
        self.hidden_layers = hidden_layers
        self.dropout = nn.Dropout(dropout_percent)
        self.lr = lr
        self.activation = activation
        self.softmax = output_activation
        self.layers = nn.ModuleList()

        # TODO add GPU option

        # input layer
        self.layers.append(nn.Linear(self.input_dim, self.hidden_units))
        # hidden layers
        for layer in range(self.hidden_layers):
            self.layers.append(nn.Linear(self.hidden_units, self.hidden_units))
        # output layer
        self.layers.append(nn.Linear(self.hidden_units, self.output_dim))

    def forward(self, X, **kwargs):
        X = self.activation(self.layers[0](X))
        X = self.dropout(X)
        for i in range(self.hidden_layers):
            X = self.activation(self.layers[i+1](X))
        X = self.softmax(self.layers[self.hidden_layers+1](X))
        return X

    def run_rhc_single_step(self, net, X_train, y_train, **fit_params):
        # copy weights
        previous_model = copy.deepcopy(net.module_)

        # calc old loss
        y_pred = net.infer(X_train, **fit_params)
        old_loss = net.get_loss(y_pred, y_train, X_train, training=False)

        # set RHC step size = lr
        step_size = self.lr

        # select random layer
        layer = np.random.randint(0, len(self.layers))-1
        input_dim = np.random.randint(0, net.module_.layers[layer].weight.shape[0])
        output_dim = np.random.randint(0, net.module_.layers[layer].weight.shape[1])
        neighbor = step_size * np.random.choice([-1, 1])

        with torch.no_grad():
            net.module_.layers[layer].weight[input_dim][output_dim] = neighbor + \
                net.module_.layers[layer].weight[input_dim][output_dim].data

        # Evaluate new loss
        y_pred = net.infer(X_train, **fit_params)
        new_loss = net.get_loss(y_pred, y_train, X_train, training=False)
        loss = new_loss

        # Revert to old weights if new loss is higher
        if new_loss > old_loss:
            net.module_ = copy.deepcopy(previous_model)
            loss = old_loss

        return loss, y_pred

    @staticmethod
    def register_rhc_training_step():
        @add_to(NeuralNet)
        def train_step_single(self, batch, **fit_params):
            self._set_training(False)
            Xi, yi = unpack_data(batch)
            # disable backprop and run custom training step
            # loss.backward()
            loss, y_pred = self.module_.run_rhc_single_step(self, Xi, yi, **fit_params)
            return {
                'loss': loss,
                'y_pred': y_pred,
            }
